"""G1 竞技场实验骨架。

M0 只跑一次演示；这里把「多子级 × 多随机种子」的对比做成可复现的实验：
每个种子跑一轮完整的竞技场（硬过滤 → 打分 → 异议 → 仲裁），
统计胜率与得分，并和同种子下的简单基线做配对比较。

基线按方案里的批评意见补：
- `single`：只看第一个子级（无竞争）；
- `majority`：把过半候选共同持有的特征拼成一个「多数票」重构再打分；
- AGH：完整竞技场（含硬过滤、异议标记、固定种子仲裁）。

统计口径与冻结层一致：配对 bootstrap CI + bootstrap p 值 + Holm 校正。
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .arena import (
    ArenaConfig,
    CompetitiveCandidate,
    arbitrate,
    evaluate_dissent,
    hard_filter,
    score_candidate,
)
from .contracts import (
    AbstractSignature,
    CoverageClaim,
    GestaltReconstruction,
    Skeleton,
)
from .evalstats import Interval, bootstrap_pvalue, holm, paired_bootstrap_ci
from .llm import ReconstructChild

BASELINES = ("single", "majority", "best_of_n")


@dataclass(frozen=True)
class Arm:
    """一个参赛子级。"""

    name: str
    child: ReconstructChild


@dataclass
class ArmStats:
    name: str
    valid: int = 0
    errors: int = 0
    wins: int = 0
    contested_wins: int = 0
    score_sum: float = 0.0

    @property
    def win_rate(self) -> float:
        return self.wins / self.valid if self.valid else 0.0

    @property
    def mean_score(self) -> float:
        return self.score_sum / self.valid if self.valid else 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "valid": self.valid,
            "errors": self.errors,
            "wins": self.wins,
            "win_rate": round(self.win_rate, 4),
            "contested_wins": self.contested_wins,
            "mean_score": round(self.mean_score, 5),
        }


@dataclass
class Comparison:
    arm: str
    baseline: str
    delta: Interval
    p_value: float
    holm_threshold: float
    significant: bool


@dataclass
class ExperimentReport:
    seeds: int
    contract_id: str
    arms: list[ArmStats]
    contested_rate: float
    comparisons: list[Comparison] = field(default_factory=list)
    skipped_seeds: int = 0
    metrics: dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "seeds": self.seeds,
            "contract_id": self.contract_id,
            "skipped_seeds": self.skipped_seeds,
            "contested_rate": round(self.contested_rate, 4),
            "metrics": {k: round(v, 4) for k, v in self.metrics.items()},
            "arms": [a.as_dict() for a in self.arms],
            "comparisons": [
                {
                    "arm": c.arm,
                    "baseline": c.baseline,
                    "delta": {"mean": round(c.delta.mean, 5), "lo": round(c.delta.lo, 5),
                              "hi": round(c.delta.hi, 5), "n": c.delta.n},
                    "p_value": round(c.p_value, 4),
                    "holm_threshold": round(c.holm_threshold, 4),
                    "significant": c.significant,
                }
                for c in self.comparisons
            ],
        }

    def write(self, path: str | Path) -> Path:
        import json

        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return target


def _majority_candidate(
    candidates: Sequence[GestaltReconstruction],
    skeleton: Skeleton,
    contract_id: str,
) -> GestaltReconstruction | None:
    """把过半候选都有的特征拼成一个多数票重构。"""
    if not candidates:
        return None
    threshold = max(1, (len(candidates) + 1) // 2)
    counts: dict[str, int] = {}
    for cand in candidates:
        for feature in set(cand.signature.features):
            counts[feature] = counts.get(feature, 0) + 1
    features = sorted(f for f, n in counts.items() if n >= threshold)
    if not features:
        return None
    parts = sorted({p for cand in candidates for p in cand.parts})
    covered = sorted({p for cand in candidates for p in cand.coverage.covered})
    confidence = sum(c.self_confidence for c in candidates) / len(candidates)
    return GestaltReconstruction(
        child_id="baseline-majority",
        contract_id=contract_id,
        skeleton_id=skeleton.skeleton_id,
        parts=parts,
        coverage=CoverageClaim(covered=covered),
        signature=AbstractSignature(signature_id="baseline-majority", features=features),
        self_confidence=confidence,
        content={"edges": [list(e) for e in skeleton.edges]},
    )


def fact_retention(candidate: GestaltReconstruction, facts: Sequence[str]) -> float:
    """关键事实保留率：父级特征与骨架必需项里，候选保住了多少。"""
    if not facts:
        return 1.0
    kept = set(candidate.signature.features) | set(candidate.parts)
    return len([f for f in facts if f in kept]) / len(facts)


def stance_entropy(candidates: Sequence[GestaltReconstruction]) -> float:
    """立场熵：候选之间对每个特征的分歧程度，归一化到 [0,1]。

    0 = 所有候选立场一致；1 = 每个特征都恰好一半支持一半反对。
    """
    if len(candidates) < 2:
        return 0.0
    features = sorted({f for c in candidates for f in c.signature.features})
    if not features:
        return 0.0
    total = 0.0
    for feature in features:
        p = sum(1 for c in candidates if feature in c.signature.features) / len(candidates)
        if 0.0 < p < 1.0:
            total += -(p * math.log2(p) + (1 - p) * math.log2(1 - p))
    return total / len(features)


def run_experiment(
    arms: Sequence[Arm],
    skeleton: Skeleton,
    cfg: ArenaConfig,
    *,
    contract_id: str = "ct-experiment",
    parent_features: Sequence[str] | None = None,
    seeds: Iterable[int] = range(100),
    resamples: int = 2_000,
    alpha: float = 0.05,
    benign_arms: Sequence[str] | None = None,
) -> ExperimentReport:
    """跑多子级竞技场实验，返回带统计结论的报告。"""
    if not arms:
        raise ValueError("至少需要一个子级")
    seed_list = list(seeds)
    parent_sig = (
        AbstractSignature(signature_id="parent-exp", features=list(parent_features))
        if parent_features
        else None
    )
    stats = {arm.name: ArmStats(name=arm.name) for arm in arms}
    records: list[dict[str, Any]] = []
    retention: list[float] = []
    entropy: list[float] = []
    benign_attempts = 0
    benign_blocked = 0
    benign = set(benign_arms) if benign_arms is not None else {arms[0].name}
    facts = list(parent_features or []) + list(skeleton.required_items)
    contested = 0
    used = 0
    skipped = 0

    for seed in seed_list:
        produced: list[tuple[Arm, GestaltReconstruction, Any]] = []
        valid_recons: list[GestaltReconstruction] = []
        arm_scores: dict[str, float] = {}
        for arm in arms:
            try:
                recon = arm.child.reconstruct(contract_id)
            except Exception:
                stats[arm.name].errors += 1
                continue
            filt = hard_filter(recon, skeleton)
            if not filt.passed:
                stats[arm.name].errors += 1
                if arm.name in benign:
                    benign_attempts += 1
                    benign_blocked += 1
                continue
            if arm.name in benign:
                benign_attempts += 1
            score = score_candidate(
                recon, skeleton, cfg, verifier_score=None, parent_signature=parent_sig
            )
            decision = evaluate_dissent(
                recon,
                score,
                pool=[list(parent_sig.features)] if parent_sig else [],
                abstractions=[],
                cfg=cfg,
            )
            produced.append((arm, recon, CompetitiveCandidate(recon, score, dissent=decision)))
            valid_recons.append(recon)
            stats[arm.name].valid += 1
            stats[arm.name].score_sum += score.score
            arm_scores[arm.name] = score.score
            retention.append(fact_retention(recon, facts))

        if not produced:
            skipped += 1
            continue
        used += 1
        entropy.append(stance_entropy(valid_recons))
        result = arbitrate([c for _, _, c in produced], seed=seed, cfg=cfg)
        if result.contested:
            contested += 1
        winner = next((arm for arm, rec, _ in produced if rec.child_id == result.winner), None)
        if winner is not None:
            stats[winner.name].wins += 1
            if result.contested:
                stats[winner.name].contested_wins += 1

        # 基线 1：只看第一个子级
        first = produced[0][1]
        record: dict[str, Any] = {
            "scores": arm_scores,
            "single": score_candidate(
                first, skeleton, cfg, verifier_score=None, parent_signature=parent_sig
            ).score,
            "best_of_n": max(arm_scores.values()),
        }
        # 基线 2：多数票重构
        majority = _majority_candidate(valid_recons, skeleton, contract_id)
        if majority is not None and hard_filter(majority, skeleton).passed:
            record["majority"] = score_candidate(
                majority, skeleton, cfg, verifier_score=None, parent_signature=parent_sig
            ).score
        records.append(record)

    comparisons: list[Comparison] = []
    pending: list[tuple[str, str, Interval, float]] = []
    for arm in arms:
        for baseline in BASELINES:
            deltas = [
                record["scores"][arm.name] - record[baseline]
                for record in records
                if arm.name in record["scores"] and baseline in record
            ]
            if len(deltas) < 2:
                continue
            ci = paired_bootstrap_ci(deltas, resamples=resamples, seed=0)
            p = bootstrap_pvalue(deltas, resamples=resamples, seed=0)
            pending.append((arm.name, baseline, ci, p))
    if pending:
        corrected = holm([p for *_, p in pending], alpha=alpha)
        by_index = {idx: (threshold, reject) for idx, threshold, reject in corrected}
        for i, (arm_name, baseline, ci, p) in enumerate(pending):
            threshold, reject = by_index[i]
            comparisons.append(
                Comparison(
                    arm=arm_name,
                    baseline=baseline,
                    delta=ci,
                    p_value=p,
                    holm_threshold=threshold,
                    significant=reject,
                )
            )

    return ExperimentReport(
        seeds=used,
        contract_id=contract_id,
        arms=list(stats.values()),
        contested_rate=(contested / used) if used else 0.0,
        comparisons=comparisons,
        skipped_seeds=skipped,
        metrics={
            "fact_retention": (sum(retention) / len(retention)) if retention else 0.0,
            "stance_entropy": (sum(entropy) / len(entropy)) if entropy else 0.0,
            "false_block_rate": (benign_blocked / benign_attempts) if benign_attempts else 0.0,
        },
    )


__all__ = [
    "BASELINES",
    "Arm",
    "ArmStats",
    "Comparison",
    "ExperimentReport",
    "run_experiment",
]
