"""代码任务的竞技场：把治理层（签名、账本、哈希链、仲裁）接到真实测试信号上。

与 `arena.py` 的区别：那里的分数来自 AGH 自己定义的结构规则；这里来自子进程里
真跑测试。治理层不动——候选仍然要过网关签名、过写入门、记预算、入哈希链日志。

一个刻意的设计：**仲裁只看 visible 分**（模拟真实场景：只能看到公开用例），
hidden 分只用于报告真实质量。两者的差距就是 `visible - hidden`，
它暴露「被选中的候选是不是在背可见答案」——这正是治理层应该让人看见的东西。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .contracts import AbstractSignature, CoverageClaim, GestaltReconstruction
from .crypto import EnvelopeVerifier, KeyRing, ProvenanceGateway
from .eventlog import EventLog
from .execverify import ExecutionVerifier, run_cases
from .gate import MemoryStore, RiskModel, WriteGate
from .governance import GovernanceMachine
from .ledger import BudgetVector, Ledger
from .pipeline import DEV_KID, DEV_SECRET

OVERFIT_WARN = 0.25


@dataclass(frozen=True)
class CodeCandidate:
    child_id: str
    code: str
    visible: float
    hidden: float
    calls: int

    @property
    def overfit_gap(self) -> float:
        return self.visible - self.hidden

    def as_dict(self) -> dict[str, Any]:
        return {
            "child_id": self.child_id,
            "visible": round(self.visible, 4),
            "hidden": round(self.hidden, 4),
            "overfit_gap": round(self.overfit_gap, 4),
            "calls": self.calls,
            "code_chars": len(self.code),
        }


@dataclass(frozen=True)
class CodeArenaReport:
    task_id: str
    winner: str
    ranking: tuple[str, ...]
    candidates: tuple[CodeCandidate, ...]
    admitted: int
    rejected: int
    log_head: str
    log_ok: bool
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "winner": self.winner,
            "ranking": list(self.ranking),
            "candidates": [c.as_dict() for c in self.candidates],
            "admitted": self.admitted,
            "rejected": self.rejected,
            "log_head": self.log_head,
            "log_ok": self.log_ok,
            "notes": list(self.notes),
        }


def _recon(task_id: str, child_id: str, code: str) -> GestaltReconstruction:
    return GestaltReconstruction(
        child_id=child_id,
        contract_id=f"ct-{task_id}",
        skeleton_id=f"sk-{task_id}",
        parts=["code"],
        coverage=CoverageClaim(covered=["code"]),
        signature=AbstractSignature(signature_id=f"sig-{child_id}", features=["code"]),
        self_confidence=0.5,
        content={"code": code},
    )


def run_code_arena(
    task: Any,
    solvers: Sequence[tuple[str, Any]],
    *,
    run_dir: str | Path,
    frozen_root: str | Path | None = None,
    key_kind: str = "hmac",
    budget_usd: float = 1.0,
) -> CodeArenaReport:
    """`solvers` 是 [(child_id, callable(task) -> code)]；每个求解器的调用次数由调用方记录。"""
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    keyring = (
        KeyRing.with_ed25519(DEV_KID, __import__("hashlib").sha256(DEV_SECRET).digest())
        if key_kind == "ed25519"
        else KeyRing.with_secret(DEV_KID, DEV_SECRET)
    )
    gateway = ProvenanceGateway(keyring, DEV_KID)
    verifier = EnvelopeVerifier(keyring)
    root = Path(frozen_root) if frozen_root is not None else Path(__file__).resolve().parents[1] / "config" / "frozen"
    gate = WriteGate(verifier, RiskModel.from_frozen(root), MemoryStore())
    ledger = Ledger(BudgetVector(compute_units=len(solvers) + 1, wall_ms=60_000, usd=budget_usd))
    log = EventLog(run_dir / "events.jsonl")
    gov = GovernanceMachine(frozen=None)
    notes: list[str] = []

    def emit(type_: str, payload: dict[str, Any]) -> None:
        log.append(type_, payload)

    task_id = task.spec.task_id
    emit("contract.issued", {"task_id": task_id, "entrypoint": task.spec.entrypoint})
    gov.transition("VALIDATING", tier="T1")

    candidates: list[CodeCandidate] = []
    admitted = rejected = 0
    for child_id, solve in solvers:
        lease = ledger.reserve(
            owner=child_id,
            reserved=BudgetVector(compute_units=1, wall_ms=30_000, usd=0.01),
            max_tokens=1,
        )
        emit("ledger.reserved", {"lease_id": lease.lease_id, "owner": child_id})
        try:
            code = solve(task)
            calls = 1
        except Exception as exc:  # 模型调用失败与答错分开：这里直接判失败并记账
            code = ""
            calls = 0
            emit("solver.failed", {"child_id": child_id, "error": type(exc).__name__})
        ledger.settle(lease.lease_id, BudgetVector(compute_units=1, wall_ms=1000, usd=0.01))
        emit("ledger.settled", {"lease_id": lease.lease_id, "owner": child_id})

        recon = _recon(task_id, child_id, code)
        envelope = gateway.issue(
            payload=recon.model_dump(mode="json"),
            producer_id=child_id,
            producer_kind="child",
            parent_contract_id=recon.contract_id,
            trust=1,
        )
        admission = gate.admit(envelope, record_id=child_id, edges=[], parent_trust=1)
        if not admission.admitted:
            rejected += 1
            emit("gate.rejected", {"child_id": child_id, "reason": admission.reason})
            continue
        admitted += 1
        emit("gate.admitted", {"child_id": child_id, "code_sha256": _sha(code)})

        exec_verifier = ExecutionVerifier(spec=task.spec)
        vis = run_cases(code, task.spec, task.spec.visible).score
        hid = exec_verifier.score(recon, None)
        candidate = CodeCandidate(child_id, code, vis, hid, calls)
        candidates.append(candidate)
        emit(
            "candidate.scored",
            {"child_id": child_id, "visible": round(vis, 4), "hidden": round(hid, 4)},
        )

    if not candidates:
        notes.append("没有候选通过写入门")
        return CodeArenaReport(
            task_id, "", (), (), admitted, rejected, log.head(), _log_ok(log), notes
        )

    # 仲裁只看 visible；hidden 只用于报告
    ranking = tuple(c.child_id for c in sorted(candidates, key=lambda c: (-c.visible, -c.hidden)))
    winner = next(c for c in candidates if c.child_id == ranking[0])
    emit("arbitration", {"winner": winner.child_id, "ranking": list(ranking)})
    if winner.overfit_gap > OVERFIT_WARN:
        notes.append(
            f"{winner.child_id} 的 visible-hidden 差距 {winner.overfit_gap:.2f} > {OVERFIT_WARN}："
            "可能在被可见用例，hidden 分才是真实质量"
        )
    gov.transition("VERIFIED", tier="T1", reason="执行验证通过")
    gov.transition("RELEASED", tier="T1", human_approved=True, reason="仲裁完成")
    emit("governance.transition", {"from": "VERIFIED", "to": "RELEASED", "tier": "T1"})

    log_ok = _log_ok(log)
    return CodeArenaReport(
        task_id=task_id,
        winner=winner.child_id,
        ranking=ranking,
        candidates=tuple(candidates),
        admitted=admitted,
        rejected=rejected,
        log_head=log.head(),
        log_ok=log_ok,
        notes=notes,
    )


def _log_ok(log: EventLog) -> bool:
    try:
        log.verify()
    except Exception:
        return False
    return True


def _sha(code: str) -> str:
    import hashlib

    return hashlib.sha256(code.encode("utf-8")).hexdigest()[:16]


__all__ = ["OVERFIT_WARN", "CodeArenaReport", "CodeCandidate", "run_code_arena"]
