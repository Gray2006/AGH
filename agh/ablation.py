"""消融套件（§4）。

方案要求「9 组消融」：完整链路 + 8 个单点关闭。这里把每个消融定义成
对 ArenaConfig 的一处改动（或关掉硬过滤/异议），跑同一批种子，
用配对 bootstrap + Holm 判断「关掉这一项，分数是否真的掉了」。

注意：规则子级下这些数字只说明链路行为，不是模型结论。
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
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
from .contracts import AbstractSignature, GestaltReconstruction, Skeleton
from .evalstats import Interval, bootstrap_pvalue, holm, paired_bootstrap_ci
from .experiment import Arm


@dataclass(frozen=True)
class Ablation:
    name: str
    description: str
    weights: dict[str, float] | None = None
    dissent_tau: float | None = None
    diversity_min_clusters: int | None = None
    dissent: bool = True
    arena: bool = True

    def config(self, cfg: ArenaConfig) -> ArenaConfig:
        weights = dict(cfg.weights)
        if self.weights:
            weights.update(self.weights)
        return replace(
            cfg,
            weights=weights,
            dissent_tau=cfg.dissent_tau if self.dissent_tau is None else self.dissent_tau,
            diversity_min_clusters=(
                cfg.diversity_min_clusters
                if self.diversity_min_clusters is None
                else self.diversity_min_clusters
            ),
        )


ABLATIONS: tuple[Ablation, ...] = (
    Ablation("no_vertical", "垂直一致性权重归零", weights={"vertical": 0.0}),
    Ablation("no_coverage", "覆盖率权重归零", weights={"coverage": 0.0}),
    Ablation("no_structural", "结构距离权重归零", weights={"structural": 0.0}),
    Ablation("no_update", "更新量权重归零", weights={"update": 0.0}),
    Ablation("no_confidence", "校准置信权重归零", weights={"confidence": 0.0}),
    Ablation("no_dissent", "异议永不成立", dissent_tau=1e9),
    Ablation("no_arena", "不做仲裁，直接取第一个候选", arena=False),
    Ablation("no_diversity", "关闭多样性门槛", diversity_min_clusters=0),
)


@dataclass
class AblationRow:
    name: str
    description: str
    delta: Interval
    p_value: float
    holm_threshold: float
    significant: bool


@dataclass
class AblationReport:
    seeds: int
    rows: list[AblationRow] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "seeds": self.seeds,
            "rows": [
                {
                    "name": r.name,
                    "description": r.description,
                    "delta": {
                        "mean": round(r.delta.mean, 5),
                        "lo": round(r.delta.lo, 5),
                        "hi": round(r.delta.hi, 5),
                        "n": r.delta.n,
                    },
                    "p_value": round(r.p_value, 4),
                    "holm_threshold": round(r.holm_threshold, 4),
                    "significant": r.significant,
                }
                for r in self.rows
            ],
        }

    def write(self, path: str | Path) -> Path:
        import json

        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return target


def _winner_score(
    arms: Sequence[Arm],
    skeleton: Skeleton,
    cfg: ArenaConfig,
    contract_id: str,
    parent_sig: AbstractSignature | None,
    seed: int,
    ablation: Ablation,
) -> float | None:
    candidates: list[CompetitiveCandidate] = []
    for arm in arms:
        try:
            recon: GestaltReconstruction = arm.child.reconstruct(contract_id)
        except Exception:
            continue
        if not hard_filter(recon, skeleton).passed:
            continue
        score = score_candidate(
            recon, skeleton, cfg, verifier_score=None, parent_signature=parent_sig
        )
        decision = None
        if ablation.dissent:
            decision = evaluate_dissent(
                recon,
                score,
                pool=[list(parent_sig.features)] if parent_sig else [],
                abstractions=[],
                cfg=cfg,
            )
        candidates.append(CompetitiveCandidate(recon, score, dissent=decision))
    if not candidates:
        return None
    if not ablation.arena:
        return candidates[0].breakdown.score
    result = arbitrate(candidates, seed=seed, cfg=cfg)
    winner = next((c for c in candidates if c.reconstruction.child_id == result.winner), None)
    if winner is None:
        # 仲裁可能因为所有候选都是 0 分而不选任何人；消融里按 0 分处理
        return 0.0
    return winner.breakdown.score


def run_ablation(
    arms: Sequence[Arm],
    skeleton: Skeleton,
    cfg: ArenaConfig,
    *,
    contract_id: str = "ct-ablation",
    parent_features: Sequence[str] | None = None,
    seeds: Iterable[int] = range(50),
    resamples: int = 2_000,
    alpha: float = 0.05,
) -> AblationReport:
    if not arms:
        raise ValueError("至少需要一个子级")
    parent_sig = (
        AbstractSignature(signature_id="parent-ablation", features=list(parent_features))
        if parent_features
        else None
    )
    full = Ablation("full", "完整链路")
    deltas: dict[str, list[float]] = {a.name: [] for a in ABLATIONS}
    used = 0
    for seed in seeds:
        base = _winner_score(arms, skeleton, cfg, contract_id, parent_sig, seed, full)
        if base is None:
            continue
        used += 1
        for ablation in ABLATIONS:
            variant = _winner_score(
                arms, skeleton, ablation.config(cfg), contract_id, parent_sig, seed, ablation
            )
            if variant is not None:
                deltas[ablation.name].append(variant - base)

    pending: list[tuple[Ablation, Interval, float]] = []
    for ablation in ABLATIONS:
        values = deltas[ablation.name]
        if len(values) < 2:
            continue
        ci = paired_bootstrap_ci(values, resamples=resamples, seed=0)
        p = bootstrap_pvalue(values, resamples=resamples, seed=0)
        pending.append((ablation, ci, p))

    rows: list[AblationRow] = []
    if pending:
        corrected = holm([p for *_, p in pending], alpha=alpha)
        by_index = {idx: (threshold, reject) for idx, threshold, reject in corrected}
        for i, (ablation, ci, p) in enumerate(pending):
            threshold, reject = by_index[i]
            rows.append(
                AblationRow(
                    name=ablation.name,
                    description=ablation.description,
                    delta=ci,
                    p_value=p,
                    holm_threshold=threshold,
                    significant=reject,
                )
            )
    return AblationReport(seeds=used, rows=rows)


__all__ = ["ABLATIONS", "Ablation", "AblationReport", "AblationRow", "run_ablation"]
