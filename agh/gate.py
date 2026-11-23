"""四节点门控 v2（§3.1 / D1、D4）。

- 写入门：验签 provenance；内容风险评分；高风险入隔离池。
- 污点传播：派生内容继承输入中最低信任等级，加工不能让信任升高。
- 检索门：除条目风险外，校验关联边与选择路径；高风险条目随机消融复核后再放行。
- 提升门：局部→共享最严；speculative_links 必须「真实任务引用 + 验收 + 复验计数」。
- 复用门：未验证引用不自动生效。

目标写成「遏制扩散」，同时统计误拦率。
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from .contracts import Provenance, SignedEnvelope, TrustLevel
from .crypto import EnvelopeVerifier, ProvenanceError, derive_trust
from .frozen import load_json


# --------------------------------------------------------------------------
# 风险模型（留在冻结层）
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class RiskModel:
    weights: dict[str, float]
    quarantine_threshold: float
    ablation_samples: int
    ablation_dissent_majority: float
    promotion_min_references: int
    promotion_min_rechecks: int

    @classmethod
    def from_frozen(cls, frozen_root: Path) -> "RiskModel":
        raw = load_json(frozen_root, "risk_model.json")
        return cls(
            weights=dict(raw["weights"]),
            quarantine_threshold=float(raw["quarantine_threshold"]),
            ablation_samples=int(raw["ablation_samples"]),
            ablation_dissent_majority=float(raw["ablation_dissent_majority"]),
            promotion_min_references=int(raw["promotion_min_references"]),
            promotion_min_rechecks=int(raw["promotion_min_rechecks"]),
        )


def risk_score(payload: dict[str, Any], trust: int, model: RiskModel) -> float:
    content = payload.get("content", {}) if isinstance(payload, dict) else {}
    score = 0.0
    if trust < int(TrustLevel.VALIDATED):
        score += model.weights["untrusted_source"]
    edges = content.get("edges", [])
    verified_edges = set(map(tuple, content.get("verified_edges", [])))
    if edges:
        unverified = [
            e for e in edges
            if not (isinstance(e, (list, tuple)) and tuple(e) in verified_edges)
        ]
        score += model.weights["unverified_edge"] * (len(unverified) / len(edges))
    if content.get("speculative_links", 0):
        score += model.weights["speculative_link"]
    if content.get("external_refs", 0):
        score += model.weights["external_reference"]
    return min(score, 1.0)


# --------------------------------------------------------------------------
# 记忆条目
# --------------------------------------------------------------------------


@dataclass
class MemoryRecord:
    record_id: str
    payload: dict[str, Any]
    trust: int
    risk: float
    provenance: Provenance | None
    edges: list[str] = field(default_factory=list)
    speculative: bool = False
    references: int = 0
    acceptances: int = 0
    rechecks: int = 0
    quarantined: bool = False
    blocked: bool = False
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Admission:
    admitted: bool
    record: MemoryRecord | None
    reason: str


class MemoryStore:
    def __init__(self) -> None:
        self.records: dict[str, MemoryRecord] = {}

    def add(self, record: MemoryRecord) -> None:
        self.records[record.record_id] = record

    def get(self, record_id: str) -> MemoryRecord:
        return self.records[record_id]

    def exists(self, record_id: str) -> bool:
        return record_id in self.records


# --------------------------------------------------------------------------
# 写入门
# --------------------------------------------------------------------------


class WriteGate:
    """验签 → 风险 → 隔离。验签失败直接拒收，不做「警告后放行」。"""

    def __init__(
        self,
        verifier: EnvelopeVerifier,
        model: RiskModel,
        store: MemoryStore,
    ) -> None:
        self.verifier = verifier
        self.model = model
        self.store = store
        self.quarantine_pool: dict[str, MemoryRecord] = {}

    def admit(
        self,
        envelope: SignedEnvelope,
        *,
        record_id: str | None = None,
        edges: Sequence[str] = (),
        parent_trust: int = int(TrustLevel.LOCAL),
    ) -> Admission:
        try:
            prov = self.verifier.verify(envelope)
        except ProvenanceError as exc:
            return Admission(False, None, f"rejected:{exc.code}")
        # 污点传播：子级产出不高于父级信任，也不高于 LOCAL
        trust = int(derive_trust([prov.trust, parent_trust, TrustLevel.LOCAL]))
        risk = risk_score(envelope.payload, trust, self.model)
        quarantined = risk >= self.model.quarantine_threshold
        record = MemoryRecord(
            record_id=record_id or prov.event_id,
            payload=envelope.payload,
            trust=int(TrustLevel.QUARANTINED) if quarantined else trust,
            risk=risk,
            provenance=prov,
            edges=list(edges),
            speculative=bool(envelope.payload.get("content", {}).get("speculative_links", 0)),
            quarantined=quarantined,
            notes=["risk>=threshold，隔离"] if quarantined else [],
        )
        if quarantined:
            record.trust = int(TrustLevel.QUARANTINED)
            self.quarantine_pool[record.record_id] = record
            return Admission(False, record, "quarantined")
        self.store.add(record)
        return Admission(True, record, "admitted")


# --------------------------------------------------------------------------
# 检索门
# --------------------------------------------------------------------------


@dataclass
class RetrievalResult:
    records: list[MemoryRecord]
    blocked: list[str]
    violations: list[str]
    false_block: int = 0


class RetrievalGate:
    """条目风险 + 关联边 + 选择路径；高风险条目要随机消融复核。

    ablation_probe：给一个条目，返回「是否恶意」的独立判定（模拟随机消融后多数裁决）。
    """

    def __init__(
        self,
        model: RiskModel,
        store: MemoryStore,
        ablation_probe: Callable[[MemoryRecord], bool] | None = None,
        seed: int = 0,
    ) -> None:
        self.model = model
        self.store = store
        self.ablation_probe = ablation_probe or (lambda r: False)
        self.rng = random.Random(seed)
        self.violations: list[str] = []
        self.false_block = 0

    def _selection_integrity(self, record: MemoryRecord) -> list[str]:
        problems: list[str] = []
        for edge in record.edges:
            if not self.store.exists(edge):
                problems.append(f"{record.record_id}:边指向不存在的条目 {edge}")
                continue
            neighbour = self.store.get(edge)
            if neighbour.trust < record.trust:
                problems.append(
                    f"{record.record_id}:边指向低信任条目 {edge}"
                    f"({neighbour.trust}<{record.trust})"
                )
            if neighbour.speculative and neighbour.rechecks == 0:
                problems.append(f"{record.record_id}:选择路径经过未复验的投机边 {edge}")
        return problems

    def _ablation(self, record: MemoryRecord) -> bool:
        votes = [self.ablation_probe(record) for _ in range(self.model.ablation_samples)]
        malicious_ratio = sum(1 for v in votes if v) / max(len(votes), 1)
        return malicious_ratio < self.model.ablation_dissent_majority

    def retrieve(self, ids: Iterable[str]) -> RetrievalResult:
        records: list[MemoryRecord] = []
        blocked: list[str] = []
        violations: list[str] = []
        for rid in ids:
            if not self.store.exists(rid):
                blocked.append(rid)
                continue
            record = self.store.get(rid)
            if record.quarantined or record.blocked:
                blocked.append(rid)
                continue
            problems = self._selection_integrity(record)
            violations.extend(problems)
            if problems:
                blocked.append(rid)
                continue
            if record.risk >= self.model.quarantine_threshold:
                if not self._ablation(record):
                    blocked.append(rid)
                    self.false_block += 1
                    continue
                record.notes.append("高风险，但随机消融复核通过")
            records.append(record)
        self.violations.extend(violations)
        return RetrievalResult(records, blocked, violations, self.false_block)


# --------------------------------------------------------------------------
# 提升门 / 复用门
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class PromotionDecision:
    allowed: bool
    reason: str


def promotion_decision(record: MemoryRecord, model: RiskModel) -> PromotionDecision:
    if record.quarantined:
        return PromotionDecision(False, "隔离条目不可提升")
    if record.speculative:
        if record.references < model.promotion_min_references:
            return PromotionDecision(False, f"真实任务引用不足({record.references})")
        if record.acceptances < 1:
            return PromotionDecision(False, "缺少验收")
        if record.rechecks < model.promotion_min_rechecks:
            return PromotionDecision(False, f"复验计数不足({record.rechecks})")
        return PromotionDecision(True, "投机边已转正")
    if record.trust < int(TrustLevel.LOCAL):
        return PromotionDecision(False, "信任等级过低")
    return PromotionDecision(True, "普通条目可进共享层")


@dataclass(frozen=True)
class ReuseDecision:
    auto_apply: bool
    requires_confirmation: bool
    reason: str


def reuse_decision(record: MemoryRecord, cited: bool) -> ReuseDecision:
    """复用门：未验证引用不自动生效。"""
    if not cited:
        return ReuseDecision(True, False, "未引用该条目")
    if record.trust >= int(TrustLevel.VALIDATED):
        return ReuseDecision(True, False, "已验证")
    return ReuseDecision(False, True, "引用未验证条目，需确认")
