"""M0 垂直切片：1 母体 + 1 父 + 3 子（规则重构器）+ 全链路。

链路顺序：
母体发骨架与契约 → 账本预留 → 子级回传（网关签名）→ 写入门验签/风险
→ 打分（校准置信、vc、覆盖率）→ 多样性预检 → 异议判定 → 纯函数仲裁
→ 治理机（T1 自动 / 异议升 T2）→ 账本结算 → 事件日志 → L1 逐位重放。

这里不接任何 LLM：子级是规则重构器，输出在日志里落全量，保证 L1 可逐位重放。
接真模型后子级输出照旧落日志，L1 仍然成立；L2 才管「重跑一次统计一致」。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .arena import (
    ArenaConfig,
    CompetitiveCandidate,
    arbitrate,
    dissent_causal_influence,
    diversity_precheck,
    evaluate_dissent,
    hard_filter,
    score_candidate,
    skeleton_violations,
    vertical_consistency,
)
from .contracts import (
    AbstractSignature,
    BudgetVector,
    ChildSubmission,
    Contract,
    CoverageClaim,
    GestaltReconstruction,
    Skeleton,
    SkeletonMove,
    TrustLevel,
)
from .crypto import EnvelopeVerifier, KeyRing, ProvenanceGateway
from .eventlog import EventLog, L1Replay, LogEntry, state_digest
from .frozen import FrozenLayer
from .gate import MemoryStore, RetrievalGate, RiskModel, WriteGate
from .governance import GovernanceConfig, GovernanceMachine
from .ledger import Ledger

DEV_KID = "gw-dev"
DEV_SECRET = b"agh-m0-dev-secret-do-not-use-in-prod"


@dataclass
class System:
    keyring: KeyRing
    gateway: ProvenanceGateway
    verifier: EnvelopeVerifier
    store: MemoryStore
    write_gate: WriteGate
    retrieval_gate: RetrievalGate
    ledger: Ledger
    governance: GovernanceMachine
    log: EventLog
    arena: ArenaConfig
    frozen: FrozenLayer


def build_system(frozen_root: Path, run_dir: Path, *, budget: BudgetVector | None = None) -> System:
    keyring = KeyRing.with_secret(DEV_KID, DEV_SECRET)
    gateway = ProvenanceGateway(keyring, DEV_KID)
    verifier = EnvelopeVerifier(keyring)
    store = MemoryStore()
    risk_model = RiskModel.from_frozen(frozen_root)
    arena_cfg = ArenaConfig.from_frozen(frozen_root)
    arena_cfg.verify_weight_sum()
    frozen = FrozenLayer(frozen_root)
    log = EventLog(run_dir / "events.jsonl")
    return System(
        keyring=keyring,
        gateway=gateway,
        verifier=verifier,
        store=store,
        write_gate=WriteGate(verifier, risk_model, store),
        retrieval_gate=RetrievalGate(risk_model, store),
        ledger=Ledger(budget or BudgetVector(compute_units=1000, wall_ms=600_000, usd=5.0)),
        governance=GovernanceMachine(frozen=frozen, config=GovernanceConfig.from_frozen(frozen_root)),
        log=log,
        arena=arena_cfg,
        frozen=frozen,
    )


# --------------------------------------------------------------------------
# 骨架与规则子级
# --------------------------------------------------------------------------


def m0_skeleton() -> Skeleton:
    return Skeleton(
        skeleton_id="sk-m0",
        nodes=["M0", "P1", "C1", "C2", "C3"],
        edges=[("M0", "P1"), ("P1", "C1"), ("P1", "C2"), ("P1", "C3")],
        required_items=["P1", "C1", "C2"],
        moves=[
            SkeletonMove(node="P1", vertical=True, declared_depth=0.5, preserved_depth=0.5),
            SkeletonMove(node="C1", vertical=True, declared_depth=1.0, preserved_depth=0.9),
            SkeletonMove(node="C2", vertical=False),
        ],
        min_vertical_moves=1,
    )


PARENT_SIG = AbstractSignature(
    signature_id="sig-parent",
    features=["M0-P1", "P1-C1", "P1-C2", "pred:hierarchical"],
)


def faithful_child(contract_id: str) -> GestaltReconstruction:
    return GestaltReconstruction(
        child_id="child-faithful",
        contract_id=contract_id,
        skeleton_id="sk-m0",
        parts=["M0", "P1", "C1", "C2", "C3"],
        coverage=CoverageClaim(covered=["P1", "C1", "C2"]),
        signature=AbstractSignature(
            signature_id="sig-faithful",
            features=["M0-P1", "P1-C1", "P1-C2", "pred:hierarchical"],
        ),
        self_confidence=0.9,
        content={
            "edges": [["M0", "P1"], ["P1", "C1"], ["P1", "C2"], ["P1", "C3"]],
            "vertical_moves": [
                {"node": "P1", "preserved_depth": 0.5},
                {"node": "C1", "preserved_depth": 0.9},
            ],
            "changed_nodes": ["C3"],
            "summary": "按父骨架补齐 C3，保留层级边",
        },
        summary="忠实重构",
    )


def shallow_child(contract_id: str) -> GestaltReconstruction:
    return GestaltReconstruction(
        child_id="child-shallow",
        contract_id=contract_id,
        skeleton_id="sk-m0",
        parts=["M0", "P1", "C1"],
        coverage=CoverageClaim(covered=["P1"]),
        signature=AbstractSignature(
            signature_id="sig-shallow",
            features=["M0-P1", "P1-C1", "pred:coverage:low"],
        ),
        self_confidence=0.6,
        content={"edges": [["M0", "P1"], ["P1", "C1"]], "changed_nodes": []},
        summary="只做了主干，覆盖率低",
    )


def dissent_child(contract_id: str) -> GestaltReconstruction:
    """与父骨架结构上明显不同的候选：平铺而非层级。"""
    return GestaltReconstruction(
        child_id="child-dissent",
        contract_id=contract_id,
        skeleton_id="sk-m0",
        parts=["M0", "P1", "C1", "C2", "C3"],
        coverage=CoverageClaim(covered=["P1", "C1", "C2"]),
        signature=AbstractSignature(
            signature_id="sig-dissent",
            features=["flat:all", "alt:no-hierarchy", "pred:independent"],
        ),
        self_confidence=0.7,
        content={
            "edges": [["M0", "P1"], ["P1", "C1"], ["P1", "C2"], ["P1", "C3"]],
            "changed_nodes": ["P1"],
            "summary": "C1/C2/C3 平铺在 M0 下，取消 P1 的中间层",
        },
        summary="异见：取消中间层",
    )


# --------------------------------------------------------------------------
# 重放 reducer
# --------------------------------------------------------------------------


def m0_reducer(state: dict[str, Any], entry: LogEntry) -> dict[str, Any]:
    """只依赖日志条目，不调用任何模型；因此可逐位重放。"""
    s = json.loads(json.dumps(state, ensure_ascii=False))
    p = entry.payload
    if entry.type == "contract.issued":
        s["contract_id"] = p["contract_id"]
        s["skeleton_id"] = p["skeleton_id"]
    elif entry.type == "ledger.reserved":
        s["leases"].append(p["lease_id"])
    elif entry.type == "gate.admitted":
        s["admitted"].append(p["record_id"])
    elif entry.type == "gate.rejected":
        s["rejected"].append(p["reason"])
    elif entry.type == "candidate.scored":
        s["scores"][p["candidate_id"]] = round(float(p["score"]), 12)
    elif entry.type == "dissent.decided":
        if p["admitted"]:
            s["dissents"].append(p["candidate_id"])
    elif entry.type == "arbitration":
        s["winner"] = p["winner"]
        s["contested"] = p["contested"]
    elif entry.type == "governance.transition":
        s["governance_state"] = p["to"]
    elif entry.type == "ledger.settled":
        s["spent_usd"] = round(s["spent_usd"] + float(p["usd"]), 12)
    elif entry.type == "skeleton.invalid":
        s["invalid_skeleton"] = p["reason"]
    return s


INITIAL_STATE: dict[str, Any] = {
    "contract_id": None,
    "skeleton_id": None,
    "leases": [],
    "admitted": [],
    "rejected": [],
    "scores": {},
    "dissents": [],
    "winner": None,
    "contested": False,
    "governance_state": "PROPOSED",
    "spent_usd": 0.0,
    "invalid_skeleton": None,
}


# --------------------------------------------------------------------------
# 运行
# --------------------------------------------------------------------------


@dataclass
class M0Report:
    winner: str | None
    contested: bool
    dissents: list[str]
    scores: dict[str, float]
    rejected: list[str]
    l1_bit_exact: bool
    governance_state: str
    ledger_violations: int
    diversity: dict[str, Any]
    influence: dict[str, Any]
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "winner": self.winner,
            "contested": self.contested,
            "dissents": self.dissents,
            "scores": self.scores,
            "rejected": self.rejected,
            "l1_bit_exact": self.l1_bit_exact,
            "governance_state": self.governance_state,
            "ledger_violations": self.ledger_violations,
            "diversity": self.diversity,
            "influence": self.influence,
            "notes": self.notes,
        }


def run_m0(
    *,
    frozen_root: Path,
    run_dir: Path,
    include_dissent: bool = True,
    forge_attempt: bool = True,
    human_approved: bool = False,
) -> M0Report:
    run_dir.mkdir(parents=True, exist_ok=True)
    system = build_system(frozen_root, run_dir)
    state = json.loads(json.dumps(INITIAL_STATE))

    def emit(type_: str, payload: dict[str, Any]) -> None:
        nonlocal state
        probe = LogEntry(
            seq=0, ts=0, type=type_, payload=payload, prev_hash="", hash=""
        )
        next_state = m0_reducer(state, probe)
        digest = state_digest(next_state)
        system.log.append(type_, {**payload, "state_digest": digest})
        state = next_state

    notes: list[str] = []
    skeleton = m0_skeleton()
    problems = skeleton_violations(skeleton, system.arena)
    if problems:
        emit("skeleton.invalid", {"reason": "; ".join(problems)})
        raise ValueError(f"骨架非法: {problems}")

    contract = Contract(
        contract_id="ct-m0-001",
        parent_id="parent-1",
        skeleton=skeleton,
        budget_max_tokens=800,
        ttl_ms=60_000,
        frozen_refs=["thresholds.json", "risk_model.json"],
    )
    emit(
        "contract.issued",
        {
            "contract_id": contract.contract_id,
            "skeleton_id": skeleton.skeleton_id,
            "required_items": skeleton.required_items,
            "n_vertical": skeleton.n_vertical,
            "vc": vertical_consistency(skeleton)[0],
        },
    )

    # ---- 账本预留（调用前预授权 max_tokens）
    children = [faithful_child, shallow_child]
    if include_dissent:
        children.append(dissent_child)
    verifier_scores = {
        "child-faithful": 0.85,
        "child-shallow": 0.50,
        "child-dissent": 0.70,
    }
    leases: dict[str, str] = {}
    for fn in children:
        recon = fn(contract.contract_id)
        lease = system.ledger.reserve(
            owner=recon.child_id,
            reserved=BudgetVector(compute_units=50, wall_ms=5_000, usd=0.2),
            max_tokens=contract.budget_max_tokens,
            key=f"reserve:{recon.child_id}",
        )
        leases[recon.child_id] = lease.lease_id
        emit(
            "ledger.reserved",
            {"lease_id": lease.lease_id, "owner": recon.child_id, "usd": lease.reserved.usd},
        )

    # ---- 子级提交（网关签名）+ 伪造尝试
    admitted: list[GestaltReconstruction] = []
    rejected: list[str] = []
    for fn in children:
        recon = fn(contract.contract_id)
        submission = ChildSubmission(
            submission_id=f"sub-{recon.child_id}",
            child_id=recon.child_id,
            contract_id=contract.contract_id,
            payload=recon,
            produced_at_ms=0,
        )
        envelope = system.gateway.issue(
            payload=submission.model_dump(mode="json"),
            producer_id=recon.child_id,
            producer_kind="child",
            parent_contract_id=contract.contract_id,
            trust=TrustLevel.LOCAL,
        )
        admission = system.write_gate.admit(
            envelope,
            record_id=recon.child_id,
            edges=[],
            parent_trust=int(TrustLevel.LOCAL),
        )
        if admission.admitted:
            admitted.append(recon)
            emit(
                "gate.admitted",
                {
                    "record_id": recon.child_id,
                    "trust": admission.record.trust,
                    "risk": round(admission.record.risk, 6),
                },
            )
        else:
            rejected.append(f"{recon.child_id}:{admission.reason}")
            emit("gate.rejected", {"reason": f"{recon.child_id}:{admission.reason}"})

    if forge_attempt:
        base = faithful_child(contract.contract_id)
        submission = ChildSubmission(
            submission_id="sub-forged",
            child_id=base.child_id,
            contract_id=contract.contract_id,
            payload=base,
            produced_at_ms=0,
        )
        envelope = system.gateway.issue(
            payload=submission.model_dump(mode="json"),
            producer_id="child-forged",
            producer_kind="child",
            parent_contract_id=contract.contract_id,
            trust=TrustLevel.LOCAL,
        )
        # 攻击：子级把自己抬高到 TRUSTED，并改写 payload（模拟越权写入 provenance）
        raw = envelope.model_dump(mode="json")
        raw["provenance"]["trust"] = int(TrustLevel.TRUSTED)
        raw["payload"]["payload"]["summary"] = "已被篡改"
        forged = type(envelope).model_validate(raw)
        admission = system.write_gate.admit(forged, record_id="child-forged")
        rejected.append(f"child-forged:{admission.reason}")
        emit("gate.rejected", {"reason": f"child-forged:{admission.reason}"})
        notes.append("伪造 provenance 的提交在写入门被拒，未进入池")

    # ---- 打分
    competitive: list[CompetitiveCandidate] = []
    diversity_source = admitted
    diversity = diversity_precheck(diversity_source, system.arena)
    for recon in admitted:
        filt = hard_filter(recon, skeleton)
        if not filt.passed:
            rejected.append(f"{recon.child_id}:hard_filter:{filt.reasons}")
            emit(
                "candidate.rejected",
                {"candidate_id": recon.child_id, "reasons": list(filt.reasons)},
            )
            continue
        breakdown = score_candidate(
            recon,
            skeleton,
            system.arena,
            verifier_score=verifier_scores[recon.child_id],
            parent_signature=PARENT_SIG,
        )
        competitive.append(
            CompetitiveCandidate(
                reconstruction=recon,
                breakdown=breakdown,
                trust=int(TrustLevel.LOCAL),
            )
        )
        emit(
            "candidate.scored",
            {
                "candidate_id": recon.child_id,
                "score": breakdown.score,
                "confidence": round(breakdown.confidence, 6),
                "vc": round(breakdown.vertical_consistency, 6),
                "coverage": round(breakdown.coverage, 6),
                "structural": round(breakdown.structural, 6),
                "update": round(breakdown.update, 6),
                "notes": list(breakdown.notes),
            },
        )

    # ---- 异议：系统计算（不采信子级自报）
    pool_features = [PARENT_SIG.features]
    for cand in competitive:
        if cand.reconstruction.child_id == "child-faithful":
            pool_features.append(cand.reconstruction.signature.features)
    updated: list[CompetitiveCandidate] = []
    for cand in competitive:
        if cand.reconstruction.child_id in {"child-faithful"}:
            updated.append(cand)
            continue
        decision = evaluate_dissent(
            cand.reconstruction,
            cand.breakdown,
            pool=pool_features,
            abstractions=[PARENT_SIG.features],
            cfg=system.arena,
        )
        emit(
            "dissent.decided",
            {
                "candidate_id": cand.reconstruction.child_id,
                "novelty": round(decision.novelty, 6),
                "admitted": decision.admitted,
                "reason": decision.reason,
            },
        )
        updated.append(
            CompetitiveCandidate(
                reconstruction=cand.reconstruction,
                breakdown=cand.breakdown,
                dissent=decision,
                trust=cand.trust,
            )
        )
    competitive = updated

    # ---- 仲裁（纯函数 + 固定种子）
    result = arbitrate(competitive, seed=7, cfg=system.arena)
    influence = dissent_causal_influence(competitive, seed=7, cfg=system.arena)
    emit(
        "arbitration",
        {
            "winner": result.winner,
            "contested": result.contested,
            "ranking": list(result.ranking),
            "dissents": list(result.dissents),
            "seed": result.seed,
        },
    )

    # ---- 治理：T1 自动；有合格异议则升 T2，等人工
    gov = system.governance
    tier = "T2" if result.contested else "T1"
    gov.transition("VALIDATING", tier="T1", reason="自动验证开始")
    emit("governance.transition", {"from": "PROPOSED", "to": "VALIDATING", "tier": "T1"})
    gov.bump_recheck()
    gov.transition("VERIFIED", tier="T1", reason="结构校验通过")
    emit("governance.transition", {"from": "VALIDATING", "to": "VERIFIED", "tier": "T1"})
    if result.contested and not human_approved:
        notes.append("存在合格异议，发布升 T2，停在 VERIFIED 等人工")
        emit(
            "governance.pending",
            {"to": "RELEASED", "tier": "T2", "reason": "异议未裁决，需人工"},
        )
    else:
        gov.transition("RELEASED", tier=tier, human_approved=human_approved, reason="仲裁完成")
        emit(
            "governance.transition",
            {"from": "VERIFIED", "to": "RELEASED", "tier": tier},
        )

    # ---- 账本结算
    for recon in admitted:
        actual = BudgetVector(compute_units=42, wall_ms=3_200, usd=0.11)
        system.ledger.settle(
            leases[recon.child_id], actual, key=f"settle:{recon.child_id}"
        )
        emit(
            "ledger.settled",
            {"lease_id": leases[recon.child_id], "usd": actual.usd, "owner": recon.child_id},
        )

    # ---- 校验：日志链 + L1 重放
    system.log.verify()
    replay = L1Replay(system.log, m0_reducer, INITIAL_STATE).run()
    if not replay.bit_exact:
        notes.append(f"L1 重放不一致: {replay.mismatches}")

    report = M0Report(
        winner=result.winner,
        contested=result.contested,
        dissents=list(result.dissents),
        scores={c.reconstruction.child_id: c.breakdown.score for c in competitive},
        rejected=rejected,
        l1_bit_exact=replay.bit_exact,
        governance_state=gov.state,
        ledger_violations=len(system.ledger.violations),
        diversity={
            "clusters": diversity.clusters,
            "min_pairwise": round(diversity.min_pairwise, 6),
            "sufficient": diversity.sufficient,
            "requested_extra": diversity.requested_extra,
        },
        influence=influence,
        notes=notes,
    )
    (run_dir / "report.json").write_text(
        json.dumps(report.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


def make_demo_frozen(tmp: Path) -> Path:
    """给测试用：拷贝冻结配置并生成锚点。"""
    import shutil

    src = Path(__file__).resolve().parents[1] / "config" / "frozen"
    dst = tmp / "frozen"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    keyring = KeyRing.with_secret(DEV_KID, DEV_SECRET)
    FrozenLayer(dst).write_anchor(tmp / "anchor.json", keyring, DEV_KID)
    return dst
