"""预算账本（D7）。

原规格三个毛病：单一数值、崩溃时预留永久占用、LLM 成本事后才知。
这里改成：
- 三维预算向量（算力 / 墙钟 / 美元）；
- 预留带 TTL 租约，超时由 reconcile 回收；
- 预留与结算都幂等（同一 key 重复调用不重复计账）；
- 调用前预授权 max_tokens；
- 实际支出超出预留时照实计账，同时追加违规事件（不静默钳制）。
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from .contracts import BudgetVector


class BudgetExceeded(Exception):
    def __init__(self, needed: BudgetVector, available: BudgetVector) -> None:
        super().__init__(
            f"预算不足：需要 {needed.model_dump()}，可用 {available.model_dump()}"
        )
        self.needed = needed
        self.available = available


@dataclass
class Lease:
    lease_id: str
    owner: str
    reserved: BudgetVector
    max_tokens: int
    created_ms: int
    ttl_ms: int
    settled: bool = False

    @property
    def expires_ms(self) -> int:
        return self.created_ms + self.ttl_ms


@dataclass
class LedgerSnapshot:
    committed: BudgetVector
    outstanding: BudgetVector
    available: BudgetVector
    active_leases: int
    violations: int


@dataclass
class LedgerViolation:
    kind: str
    owner: str
    detail: dict[str, Any] = field(default_factory=dict)


class Ledger:
    def __init__(
        self,
        budget: BudgetVector,
        clock: Callable[[], int] | None = None,
        default_ttl_ms: int = 60_000,
    ) -> None:
        self.budget = budget
        self._clock = clock or (lambda: int(time.time() * 1000))
        self.default_ttl_ms = default_ttl_ms
        self._committed = BudgetVector()
        self._leases: dict[str, Lease] = {}
        self._by_key: dict[str, str] = {}
        self._settled: dict[str, BudgetVector] = {}
        self.violations: list[LedgerViolation] = []

    # ------------------------------------------------------------ 内部
    def _outstanding(self) -> BudgetVector:
        total = BudgetVector()
        for lease in self._leases.values():
            if not lease.settled:
                total = total + lease.reserved
        return total

    def _available(self) -> BudgetVector:
        out = self._outstanding()
        return BudgetVector(
            compute_units=max(0.0, self.budget.compute_units - self._committed.compute_units - out.compute_units),
            wall_ms=max(0, self.budget.wall_ms - self._committed.wall_ms - out.wall_ms),
            usd=max(0.0, self.budget.usd - self._committed.usd - out.usd),
        )

    def snapshot(self) -> LedgerSnapshot:
        return LedgerSnapshot(
            committed=self._committed,
            outstanding=self._outstanding(),
            available=self._available(),
            active_leases=sum(1 for x in self._leases.values() if not x.settled),
            violations=len(self.violations),
        )

    # ------------------------------------------------------------ 预留
    def reserve(
        self,
        *,
        owner: str,
        reserved: BudgetVector,
        max_tokens: int,
        key: str | None = None,
        ttl_ms: int | None = None,
    ) -> Lease:
        if max_tokens <= 0:
            raise ValueError("max_tokens 必须为正：调用前必须预授权")
        if key is not None and key in self._by_key:
            return self._leases[self._by_key[key]]
        available = self._available()
        if not reserved.le(available):
            raise BudgetExceeded(reserved, available)
        lease = Lease(
            lease_id=f"lease-{uuid.uuid4().hex[:10]}",
            owner=owner,
            reserved=reserved,
            max_tokens=max_tokens,
            created_ms=self._clock(),
            ttl_ms=ttl_ms if ttl_ms is not None else self.default_ttl_ms,
        )
        self._leases[lease.lease_id] = lease
        if key is not None:
            self._by_key[key] = lease.lease_id
        return lease

    # ------------------------------------------------------------ 结算
    def settle(
        self, lease_id: str, actual: BudgetVector, key: str | None = None
    ) -> BudgetVector:
        if key is not None and key in self._settled:
            return self._settled[key]
        lease = self._leases.get(lease_id)
        if lease is None:
            raise KeyError(f"未知租约: {lease_id}")
        if lease.settled:
            # 已结算过，返回结算金额，不重复计账
            return self._settled.get(lease.lease_id, BudgetVector())
        if actual.usd > lease.reserved.usd or actual.compute_units > lease.reserved.compute_units:
            self.violations.append(
                LedgerViolation(
                    kind="over_reserved",
                    owner=lease.owner,
                    detail={
                        "reserved": lease.reserved.model_dump(),
                        "actual": actual.model_dump(),
                    },
                )
            )
        self._committed = self._committed + actual
        lease.settled = True
        self._settled[lease.lease_id] = actual
        if key is not None:
            self._settled[key] = actual
        if not self._committed.le(self.budget):
            self.violations.append(
                LedgerViolation(
                    kind="over_budget",
                    owner=lease.owner,
                    detail={"committed": self._committed.model_dump()},
                )
            )
        return actual

    def release(self, lease_id: str) -> None:
        lease = self._leases.get(lease_id)
        if lease is None:
            raise KeyError(f"未知租约: {lease_id}")
        lease.settled = True  # 释放＝不再占预留，但没有支出

    # ------------------------------------------------------------ 回收
    def reconcile(self, now_ms: int | None = None) -> list[str]:
        """回收超时租约，幂等：重复调用不会重复计数。"""
        now = now_ms if now_ms is not None else self._clock()
        reclaimed: list[str] = []
        for lease in self._leases.values():
            if not lease.settled and lease.expires_ms <= now:
                lease.settled = True
                reclaimed.append(lease.lease_id)
        return reclaimed
