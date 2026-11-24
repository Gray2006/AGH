"""竞争回路 v2（§3.2 / D3、D4、D5、D6）。

修的三处致命问题：
- vertical_consistency 原来在无垂直移动时除零；若取 1，纯水平轨迹反而满分 → 现在取 0。
- dissent 原来由子级自报，可刷量 → 现在由系统算结构距离。
- confidence 原来由子级自报直接进评分 → 现在先过校准矩阵，并给独立验证器大权重。

另外补两条：
- 竞争前先检查候选初始多样性（Demystifying MAD：辩论常不如多数投票，初始多样性是关键）。
- 仲裁是纯函数 + 固定种子；异议因果影响度用「移除异议再仲裁」算，可复现。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Any

from .contracts import AbstractSignature, GestaltReconstruction, Skeleton
from .frozen import load_json


class InvalidSkeleton(Exception):
    pass


# --------------------------------------------------------------------------
# 配置
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Calibration:
    bins: tuple[tuple[float, float, float], ...]
    verifier_weight: float
    self_report_weight: float

    def lookup(self, self_confidence: float) -> float:
        for lo, hi, value in self.bins:
            if lo <= self_confidence < hi:
                return value
        return self.bins[-1][2]

    def combine(self, self_confidence: float, verifier_score: float | None) -> float:
        """D5：自报值只占小权重；没有独立验证信号时不给置信分。"""
        if verifier_score is None:
            return 0.0
        cal = self.lookup(self_confidence)
        total = self.verifier_weight + self.self_report_weight
        return (self.verifier_weight * verifier_score + self.self_report_weight * cal) / total


@dataclass(frozen=True)
class ArenaConfig:
    weights: dict[str, float]
    dissent_tau: float
    dissent_score_floor: float
    top_k: int
    diversity_min_pairwise: float
    diversity_min_clusters: int
    oversample_factor: int
    min_vertical_moves: int
    calibration: Calibration

    @classmethod
    def from_frozen(cls, frozen_root: Path) -> ArenaConfig:
        raw = load_json(frozen_root, "thresholds.json")
        arena = raw["arena"]
        cal = raw["calibration"]
        return cls(
            weights=dict(arena["weights"]),
            dissent_tau=float(arena["dissent_tau"]),
            dissent_score_floor=float(arena["dissent_score_floor"]),
            top_k=int(arena["top_k"]),
            diversity_min_pairwise=float(arena["diversity_min_pairwise"]),
            diversity_min_clusters=int(arena["diversity_min_clusters"]),
            oversample_factor=int(arena["oversample_factor"]),
            min_vertical_moves=int(arena["min_vertical_moves"]),
            calibration=Calibration(
                bins=tuple(tuple(b) for b in cal["bins"]),
                verifier_weight=float(cal["verifier_weight"]),
                self_report_weight=float(cal["self_report_weight"]),
            ),
        )

    def verify_weight_sum(self) -> None:
        total = sum(self.weights.values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"权重和不为 1: {total}")


# --------------------------------------------------------------------------
# 骨架与结构距离
# --------------------------------------------------------------------------


def skeleton_violations(skeleton: Skeleton, cfg: ArenaConfig) -> list[str]:
    problems: list[str] = []
    if not skeleton.required_items:
        problems.append("required_items 为空：覆盖率无定义，skeleton 非法")
    if skeleton.n_vertical < max(cfg.min_vertical_moves, 1):
        problems.append(
            f"垂直移动 {skeleton.n_vertical} 少于下限 {cfg.min_vertical_moves}：vc 不可信"
        )
    return problems


def structural_distance(parent_features: set[str], child_features: set[str]) -> float:
    """1 - Jaccard。两边都空视为完全相同（距离 0）。"""
    if not parent_features and not child_features:
        return 0.0
    inter = len(parent_features & child_features)
    union = len(parent_features | child_features)
    if union == 0:
        return 0.0
    return 1.0 - inter / union


# --------------------------------------------------------------------------
# 打分
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class HardFilter:
    passed: bool
    reasons: tuple[str, ...] = ()

    @classmethod
    def ok(cls) -> HardFilter:
        return cls(True, ())


def hard_filter(candidate: GestaltReconstruction, skeleton: Skeleton) -> HardFilter:
    """硬过滤：结构合法性、覆盖完整性、签名特征非空。"""
    reasons: list[str] = []
    unknown = [p for p in candidate.parts if p not in set(skeleton.nodes)]
    if unknown:
        reasons.append(f"parts 含骨架外节点: {unknown}")
    missing = [r for r in skeleton.required_items if r not in candidate.parts]
    if missing:
        reasons.append(f"parts 缺必需项: {missing}")
    if not candidate.signature.features:
        reasons.append("缺少结构签名，无法计算异议距离")
    return HardFilter(not reasons, tuple(reasons))


@dataclass(frozen=True)
class ScoreBreakdown:
    candidate_id: str
    confidence: float
    structural: float
    update: float
    vertical_consistency: float
    coverage: float
    score: float
    n_vertical: int
    unverified: bool = False
    notes: tuple[str, ...] = ()


def _child_edges(candidate: GestaltReconstruction) -> set[tuple[str, str]]:
    edges = candidate.content.get("edges", [])
    out: set[tuple[str, str]] = set()
    for edge in edges:
        if isinstance(edge, (list, tuple)) and len(edge) == 2:
            out.add((str(edge[0]), str(edge[1])))
    return out


def _parent_edges(skeleton: Skeleton) -> set[tuple[str, str]]:
    return {(a, b) for a, b in skeleton.edges}


def vertical_consistency(
    skeleton: Skeleton, candidate: GestaltReconstruction | None = None
) -> tuple[float, int]:
    """D3：n_vertical == 0 时取 0，不取 1，也不除零。

    给了 candidate 就按候选实际保留的深度算：候选没报某个垂直移动按 0 计，
    缺得越多分数越低；不给则退回只看骨架声明（兼容旧调用）。
    """
    vertical = [m for m in skeleton.moves if m.vertical]
    if not vertical:
        return 0.0, 0
    reported: dict[str, float] = {}
    if candidate is not None:
        for move in candidate.content.get("vertical_moves", []) or []:
            if isinstance(move, dict) and "node" in move:
                reported[str(move["node"])] = float(move.get("preserved_depth", 0.0))
            elif isinstance(move, str):
                # 只报了节点名：深度未知，按声明深度算，不因格式差异扣分
                reported[move] = float("nan")
    deltas = []
    for m in vertical:
        if candidate is None:
            preserved = m.preserved_depth
        else:
            value = reported.get(m.node, 0.0)
            preserved = m.declared_depth if value != value else value  # NaN 表示只报了节点
        deltas.append(abs(m.declared_depth - preserved))
    return 1.0 - sum(deltas) / len(deltas), len(vertical)


def score_candidate(
    candidate: GestaltReconstruction,
    skeleton: Skeleton,
    cfg: ArenaConfig,
    *,
    verifier_score: float | None = None,
    parent_signature: AbstractSignature | None = None,
) -> ScoreBreakdown:
    if not skeleton.required_items:
        raise InvalidSkeleton("required_items 为空，覆盖率无定义")
    f = hard_filter(candidate, skeleton)
    if not f.passed:
        raise InvalidSkeleton(f"候选未过硬过滤: {f.reasons}")

    confidence = cfg.calibration.combine(candidate.self_confidence, verifier_score)
    unverified = verifier_score is None

    parent_feats = set(parent_signature.features) if parent_signature else {
        str(e) for e in _parent_edges(skeleton)
    }
    child_feats = set(candidate.signature.features)
    structural = structural_distance(parent_feats, child_feats)

    parent_edges = _parent_edges(skeleton)
    child_edges = _child_edges(candidate)
    if parent_edges:
        edge_inter = len(parent_edges & child_edges)
        edge_union = len(parent_edges | child_edges)
        structural = 0.5 * structural + 0.5 * (1.0 - edge_inter / max(edge_union, 1))

    nodes = set(skeleton.nodes)
    changed = candidate.content.get("changed_nodes", [])
    changed = [c for c in changed if c in nodes]
    update = len(changed) / max(len(nodes), 1)

    vc, n_vertical = vertical_consistency(skeleton, candidate)
    vc_gated = verifier_score is None
    if vc_gated:
        # 垂直移动是候选自报的；没有验证器信号就不计分，否则自报即可刷分
        vc = 0.0
    # coverage = recall * precision: counting only required hits lets a candidate
    # stuff every node into covered and take full marks for free.
    required = set(skeleton.required_items)
    covered_set = {c for c in candidate.coverage.covered if c in nodes}
    hit = len(covered_set & required)
    recall = hit / len(required)
    precision = hit / len(covered_set) if covered_set else 0.0
    coverage = recall * precision

    w = cfg.weights
    score = (
        w["confidence"] * confidence
        - w["structural"] * structural
        - w["update"] * update
        + w["vertical"] * vc
        + w["coverage"] * coverage
    )
    notes: list[str] = ["无验证器信号：垂直一致性不计分"] if vc_gated and n_vertical else []
    if unverified:
        notes.append("无独立验证信号，置信分记 0")
    if n_vertical == 0:
        notes.append("无垂直移动，vc 记 0（不是 1）")
    if covered_set and precision < 1.0:
        notes.append(f"over-coverage penalty: precision {precision:.2f}")
    return ScoreBreakdown(
        candidate_id=candidate.child_id,
        confidence=confidence,
        structural=structural,
        update=update,
        vertical_consistency=vc,
        coverage=coverage,
        score=score,
        n_vertical=n_vertical,
        unverified=unverified,
        notes=tuple(notes),
    )


# --------------------------------------------------------------------------
# 异议（系统计算，D4）
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class DissentDecision:
    candidate_id: str
    novelty: float
    admitted: bool
    reason: str


def dissent_distance(
    candidate: GestaltReconstruction,
    pool: Sequence[Iterable[str]],
    abstractions: Sequence[Iterable[str]],
) -> float:
    feats = set(candidate.signature.features)
    reference: list[set[str]] = [set(x) for x in pool] + [set(x) for x in abstractions]
    if not reference:
        return 1.0  # 没有参照物时不构成「新」，但也不该判 0；由调用方决定
    return min(structural_distance(set(x), feats) for x in reference)


def evaluate_dissent(
    candidate: GestaltReconstruction,
    breakdown: ScoreBreakdown,
    *,
    pool: Sequence[Iterable[str]],
    abstractions: Sequence[Iterable[str]],
    cfg: ArenaConfig,
) -> DissentDecision:
    filt = hard_filter(candidate, Skeleton(
        skeleton_id="probe",
        nodes=list(candidate.parts),
        required_items=list(candidate.parts),
    ))
    if not filt.passed:
        return DissentDecision(candidate.child_id, 0.0, False, f"hard_filter:{filt.reasons}")
    novelty = dissent_distance(candidate, pool, abstractions)
    if breakdown.score < cfg.dissent_score_floor:
        return DissentDecision(candidate.child_id, novelty, False, "score_below_floor")
    if novelty <= cfg.dissent_tau:
        return DissentDecision(candidate.child_id, novelty, False, "novelty_below_tau")
    return DissentDecision(candidate.child_id, novelty, True, "admitted")


# --------------------------------------------------------------------------
# 多样性预检
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class DiversityReport:
    clusters: int
    min_pairwise: float
    sufficient: bool
    requested_extra: int


def diversity_precheck(
    candidates: Sequence[GestaltReconstruction], cfg: ArenaConfig
) -> DiversityReport:
    feats = [set(c.signature.features) for c in candidates]
    if not feats:
        return DiversityReport(0, 0.0, False, cfg.oversample_factor)
    clusters: list[set[str]] = []
    min_pair = 1.0
    for a, b in combinations(feats, 2):
        min_pair = min(min_pair, structural_distance(a, b))
    for f in feats:
        placed = False
        for cluster in clusters:
            if structural_distance(cluster, f) < cfg.diversity_min_pairwise:
                cluster |= f
                placed = True
                break
        if not placed:
            clusters.append(set(f))
    sufficient = len(clusters) >= cfg.diversity_min_clusters
    extra = 0 if sufficient else max(1, len(candidates) * (cfg.oversample_factor - 1))
    return DiversityReport(
        clusters=len(clusters),
        min_pairwise=min_pair if len(feats) > 1 else 1.0,
        sufficient=sufficient,
        requested_extra=extra,
    )


# --------------------------------------------------------------------------
# 仲裁（纯函数）
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class CompetitiveCandidate:
    reconstruction: GestaltReconstruction
    breakdown: ScoreBreakdown
    dissent: DissentDecision | None = None
    trust: int = 1


@dataclass(frozen=True)
class ArbitrationResult:
    winner: str | None
    ranking: tuple[str, ...]
    contested: bool
    dissents: tuple[str, ...]
    seed: int


def _tiebreak(seed: int, candidate_id: str) -> str:
    return hashlib.sha256(f"{seed}:{candidate_id}".encode()).hexdigest()


def arbitrate(
    candidates: Sequence[CompetitiveCandidate],
    *,
    seed: int,
    cfg: ArenaConfig,
) -> ArbitrationResult:
    """纯函数：相同输入 + 相同种子 → 相同结果。异议不改名次，但把结论标成 contested。"""
    eligible = [c for c in candidates if c.breakdown.score >= cfg.dissent_score_floor]
    if not eligible:
        return ArbitrationResult(None, (), False, (), seed)
    ranking = sorted(
        eligible,
        key=lambda c: (-c.breakdown.score, _tiebreak(seed, c.reconstruction.child_id)),
    )
    dissents = tuple(
        c.reconstruction.child_id
        for c in candidates
        if c.dissent is not None and c.dissent.admitted
    )
    return ArbitrationResult(
        winner=ranking[0].reconstruction.child_id,
        ranking=tuple(c.reconstruction.child_id for c in ranking),
        contested=bool(dissents),
        dissents=dissents,
        seed=seed,
    )


def dissent_causal_influence(
    candidates: Sequence[CompetitiveCandidate],
    *,
    seed: int,
    cfg: ArenaConfig,
) -> dict[str, Any]:
    """移除异议再仲裁：异议是否改变了结论。可复现，回答「异议有没有用」。"""
    base = arbitrate(candidates, seed=seed, cfg=cfg)
    report: dict[str, Any] = {}
    for cid in base.dissents:
        reduced = [c for c in candidates if c.reconstruction.child_id != cid]
        alt = arbitrate(reduced, seed=seed, cfg=cfg)
        report[cid] = {
            "winner_changed": alt.winner != base.winner,
            "contested_removed": not alt.contested,
            "base_winner": base.winner,
            "alt_winner": alt.winner,
        }
    return report


def arena_report(
    candidates: Sequence[CompetitiveCandidate], result: ArbitrationResult
) -> dict[str, Any]:
    return {
        "seed": result.seed,
        "winner": result.winner,
        "ranking": list(result.ranking),
        "contested": result.contested,
        "dissents": list(result.dissents),
        "scores": {
            c.reconstruction.child_id: json.loads(json.dumps(c.breakdown.__dict__, default=str))
            for c in candidates
        },
    }
