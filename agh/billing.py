"""外部计费接入。

账本只管「预算内不超支」，钱实际怎么扣是外部系统的事。这里定义最小接口：
结算时把实际支出交给 BillingProvider，拿回可核对的收据；按 ref 幂等，重放不会重复扣款。

后端：NullBilling（不扣）、JsonFileBilling（落盘收据）、HttpBilling（POST 外部计费）。
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .contracts import BudgetVector
from .ledger import Ledger
from .netutil import open_http


@dataclass(frozen=True)
class Receipt:
    receipt_id: str
    provider: str
    ref: str
    amount_usd: float
    issued_at_ms: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "receipt_id": self.receipt_id,
            "provider": self.provider,
            "ref": self.ref,
            "amount_usd": self.amount_usd,
            "issued_at_ms": self.issued_at_ms,
        }


class BillingProvider(Protocol):
    name: str

    def charge(self, amount_usd: float, ref: str) -> Receipt: ...


class NullBilling:
    name = "null"

    def charge(self, amount_usd: float, ref: str) -> Receipt:
        return Receipt(f"null-{ref}", self.name, ref, amount_usd, int(time.time() * 1000))


class JsonFileBilling:
    """把收据追加到 JSONL；同一 ref 只扣一次。"""

    name = "json-file"

    def __init__(self, path: str | Path, clock: Callable[[], int] | None = None) -> None:
        self.path = Path(path)
        self._clock = clock or (lambda: int(time.time() * 1000))
        self._seen: dict[str, Receipt] = {}
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    data = json.loads(line)
                    self._seen[data["ref"]] = Receipt(**data)

    def charge(self, amount_usd: float, ref: str) -> Receipt:
        if ref in self._seen:
            return self._seen[ref]
        receipt = Receipt(
            receipt_id=f"rcpt-{len(self._seen) + 1:06d}",
            provider=self.name,
            ref=ref,
            amount_usd=amount_usd,
            issued_at_ms=self._clock(),
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(receipt.as_dict(), ensure_ascii=False) + "\n")
        self._seen[ref] = receipt
        return receipt


Transport = Callable[[str, str, dict[str, Any] | None], dict[str, Any]]


def _urllib_transport(method: str, url: str, payload: dict[str, Any] | None) -> dict[str, Any]:
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    with open_http(url, data=data, headers=headers, method=method, timeout=15) as resp:
        return json.loads(resp.read().decode())


class HttpBilling:
    """POST {amount_usd, ref} 到外部计费服务，返回收据字段。"""

    name = "http"

    def __init__(self, url: str, transport: Transport | None = None) -> None:
        self.url = url
        self._transport = transport or _urllib_transport

    def charge(self, amount_usd: float, ref: str) -> Receipt:
        data = self._transport("POST", self.url, {"amount_usd": amount_usd, "ref": ref})
        return Receipt(
            receipt_id=str(data.get("receipt_id", f"http-{ref}")),
            provider=str(data.get("provider", self.name)),
            ref=ref,
            amount_usd=float(data.get("amount_usd", amount_usd)),
            issued_at_ms=int(data.get("issued_at_ms", int(time.time() * 1000))),
        )


class BillingLedger:
    """账本 + 外部计费：先结算预算，再按 ref 幂等扣款。"""

    def __init__(self, ledger: Ledger, provider: BillingProvider) -> None:
        self.ledger = ledger
        self.provider = provider
        self.receipts: dict[str, Receipt] = {}

    def settle(
        self, lease_id: str, actual: BudgetVector, key: str | None = None
    ) -> tuple[BudgetVector, Receipt | None]:
        settled = self.ledger.settle(lease_id, actual, key=key)
        ref = key or lease_id
        if ref in self.receipts:
            return settled, self.receipts[ref]
        if actual.usd <= 0:
            return settled, None
        receipt = self.provider.charge(actual.usd, ref)
        self.receipts[ref] = receipt
        return settled, receipt


__all__ = [
    "BillingLedger",
    "BillingProvider",
    "HttpBilling",
    "JsonFileBilling",
    "NullBilling",
    "Receipt",
]
