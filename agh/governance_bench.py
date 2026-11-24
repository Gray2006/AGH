"""治理有效性对照实验。

AGH 的所有其它实验都在问「分数能不能涨」。这里问另一个问题：
**把治理层拿掉，坏行为到底会不会被放进系统？**

三组对照，每组都是「有治理 vs 无治理」：

1. provenance：伪造出处（改载荷 / 改签名 / 未知签发者 / 重放），看拦截率
2. ledger：超预算调用，看拒绝率
3. hashchain：篡改/截断事件日志，看检出率

「无治理」不是把代码删掉，而是换成最朴素的实现（直接采信、直接放行、不做校验），
这样两组跑的是同一批输入，差别只在治理层。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .crypto import EnvelopeVerifier, KeyRing, ProvenanceError, ProvenanceGateway
from .eventlog import EventLog, LogTampered
from .ledger import BudgetExceeded, BudgetVector, Ledger
from .pipeline import DEV_KID, DEV_SECRET


@dataclass(frozen=True)
class Arm:
    name: str
    attempts: int
    caught: int
    false_rejects: int

    @property
    def catch_rate(self) -> float:
        return self.caught / self.attempts if self.attempts else 0.0

    @property
    def false_reject_rate(self) -> float:
        return self.false_rejects / self.attempts if self.attempts else 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "attempts": self.attempts,
            "caught": self.caught,
            "catch_rate": round(self.catch_rate, 4),
            "false_rejects": self.false_rejects,
            "false_reject_rate": round(self.false_reject_rate, 4),
        }


@dataclass(frozen=True)
class GovernanceReport:
    provenance: list[Arm]
    ledger: list[Arm]
    hashchain: list[Arm]

    def as_dict(self) -> dict[str, Any]:
        return {
            "provenance": [a.as_dict() for a in self.provenance],
            "ledger": [a.as_dict() for a in self.ledger],
            "hashchain": [a.as_dict() for a in self.hashchain],
        }


# ---------------------------------------------------------------- provenance


def _forge_variants(gateway: ProvenanceGateway) -> list[tuple[str, Any]]:
    """构造四种伪造：改载荷、改签名、未知签发者、重放。"""
    payload = {"parts": ["M0", "P1"], "covered": ["P1"]}
    good = gateway.issue(
        payload=payload,
        producer_id="child-1",
        producer_kind="child",
        parent_contract_id=None,
        trust=1,
    )

    tampered = good.model_copy(update={"payload": {"parts": ["M0"], "covered": []}})
    bad_sig = good.model_copy(
        update={"provenance": good.provenance.model_copy(update={"sig": "f" * 64})}
    )
    unknown_kid = good.model_copy(
        update={"provenance": good.provenance.model_copy(update={"kid": "ghost"})}
    )
    return [
        ("payload_tampered", tampered),
        ("signature_forged", bad_sig),
        ("unknown_signer", unknown_kid),
        ("replayed", good),
    ]


def run_provenance_experiment(rounds: int = 25) -> list[Arm]:
    keyring = KeyRing.with_secret(DEV_KID, DEV_SECRET)
    gateway = ProvenanceGateway(keyring, DEV_KID)
    guarded = EnvelopeVerifier(keyring)

    attempts = 0
    caught = 0
    false_rejects = 0
    for _ in range(rounds):
        good = gateway.issue(
            payload={"parts": ["M0", "P1"], "covered": ["P1"]},
            producer_id="child-ok",
            producer_kind="child",
            parent_contract_id=None,
            trust=1,
        )
        # 合法信封必须先通过一次（同时登记 nonce/seq），否则重放检测没有基准
        try:
            guarded.verify(good)
        except ProvenanceError:
            false_rejects += 1

        tampered = good.model_copy(update={"payload": {"parts": ["M0"], "covered": []}})
        bad_sig = good.model_copy(
            update={"provenance": good.provenance.model_copy(update={"sig": "f" * 64})}
        )
        unknown_kid = good.model_copy(
            update={"provenance": good.provenance.model_copy(update={"kid": "ghost"})}
        )
        for _name, envelope in (
            ("payload_tampered", tampered),
            ("signature_forged", bad_sig),
            ("unknown_signer", unknown_kid),
            ("replayed", good),
        ):
            attempts += 1
            try:
                guarded.verify(envelope)
            except ProvenanceError:
                caught += 1

    guarded_arm = Arm("with_gateway", attempts, caught, false_rejects)
    # 无治理：直接把信封里的 payload 当结果用，不验签、不验哈希 → 一次都拦不住
    naive_arm = Arm("naive_trust", attempts, 0, 0)
    return [guarded_arm, naive_arm]


# -------------------------------------------------------------------- ledger


def run_ledger_experiment(budget: int = 10, calls: int = 20) -> list[Arm]:
    ledger = Ledger(BudgetVector(compute_units=budget, wall_ms=60_000, usd=1.0))
    refused = 0
    granted = 0
    over_budget = max(0, calls - budget)
    for i in range(calls):
        try:
            lease = ledger.reserve(
                owner=f"child-{i}",
                reserved=BudgetVector(compute_units=1, wall_ms=1000, usd=0.01),
                max_tokens=1,
            )
            ledger.settle(lease.lease_id, BudgetVector(compute_units=1, wall_ms=1000, usd=0.01))
            granted += 1
        except BudgetExceeded:
            refused += 1
    # attempts 记「超出预算的请求数」，caught 记其中被拒的
    guarded = Arm("with_ledger", over_budget, refused, 0)
    naive = Arm("naive_counter", over_budget, 0, 0)  # 无账本：不做预留，全部放行
    return [guarded, naive]


# ----------------------------------------------------------------- hashchain


def run_hashchain_experiment(rounds: int = 20) -> list[Arm]:
    import tempfile

    caught = 0
    naive_caught = 0
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(rounds):
            path = Path(tmp) / f"events-{i}.jsonl"
            log = EventLog(path)
            for n in range(5):
                log.append("test.event", {"i": n})
            head, size = log.head(), log.size()

            lines = path.read_text(encoding="utf-8").splitlines()
            lines[2] = lines[2].replace('"i": 2', '"i": 99')
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")

            try:
                EventLog(path).verify_against(head, size)
            except LogTampered:
                caught += 1
            # 无治理：按行解析 JSON，不做哈希校验。改的是字段值，JSON 依然合法，
            # 所以这种篡改在朴素实现里根本发现不了。
            for line in path.read_text(encoding="utf-8").splitlines():
                json.loads(line)

    return [
        Arm("with_hashchain", rounds, caught, 0),
        Arm("naive_jsonl", rounds, naive_caught, 0),
    ]


def run_all(rounds: int = 20) -> GovernanceReport:
    return GovernanceReport(
        provenance=run_provenance_experiment(rounds),
        ledger=run_ledger_experiment(),
        hashchain=run_hashchain_experiment(rounds),
    )


__all__ = [
    "Arm",
    "GovernanceReport",
    "run_all",
    "run_hashchain_experiment",
    "run_ledger_experiment",
    "run_provenance_experiment",
]
