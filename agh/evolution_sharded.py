"""结合方案：分片精英 + 全局参数进化。

两条思路各补一半：
- 分片（方向 2）：每个基准有自己的精英档案，解决「一套特征集适配不了异构基准」；
- 参数（方向 1）：评分权重、异议 τ、多样性门槛是跨基准共享的，进化它们有真实梯度。

外层交替：固定参数跑分片进化 → 用分片整体均值评估参数变异 → 接受更好的参数 → 再分片。
这样既保留每基准的专业化，又让全局评分口径本身可被进化。

评估全部是本地规则打分，不花模型 token；LLM 变异器可选地替换分片层。
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from .arena import ArenaConfig
from .benchmarks import feature_pool
from .evalstats import Interval, paired_bootstrap_ci
from .evolution import (
    Benchmark,
    EvolutionConfig,
    Strategy,
    evolve,
)

PARAM_BOUNDS = {
    "confidence": (0.05, 0.6),
    "structural": (0.05, 0.5),
    "update": (0.0, 0.3),
    "vertical": (0.05, 0.5),
    "coverage": (0.05, 0.4),
}


@dataclass(frozen=True)
class ParamGenome:
    weights: dict[str, float]
    dissent_tau: float = 0.3
    diversity_min_clusters: int = 2

    @classmethod
    def from_config(cls, cfg: ArenaConfig) -> ParamGenome:
        return cls(weights=dict(cfg.weights), dissent_tau=cfg.dissent_tau)

    def config(self, cfg: ArenaConfig) -> ArenaConfig:
        return replace(
            cfg,
            weights=dict(self.weights),
            dissent_tau=self.dissent_tau,
            diversity_min_clusters=self.diversity_min_clusters,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "weights": {k: round(v, 3) for k, v in self.weights.items()},
            "dissent_tau": self.dissent_tau,
            "diversity_min_clusters": self.diversity_min_clusters,
        }


def mutate_params(
    parent: ParamGenome,
    rng: random.Random,
    *,
    scale: float = 0.05,
) -> ParamGenome:
    """变异 1–2 个权重；τ 以一半概率微调。scale 由退火调度给出。"""
    weights = dict(parent.weights)
    keys = rng.sample(sorted(weights), k=min(2, len(weights)) if rng.random() < 0.3 else 1)
    for key in keys:
        lo, hi = PARAM_BOUNDS.get(key, (0.0, 1.0))
        delta = scale * rng.choice([-1.0, 1.0])
        weights[key] = round(min(hi, max(lo, weights[key] + delta)), 4)
    tau = parent.dissent_tau
    if rng.random() < 0.5:
        tau = round(min(0.9, max(0.05, parent.dissent_tau + scale * rng.choice([-1.0, 1.0]))), 3)
    return ParamGenome(weights=weights, dissent_tau=tau)


def anneal_scale(round_index: int, rounds: int) -> float:
    """前半程粗搜（0.1），后半程细搜（0.02）。"""
    if rounds <= 1:
        return 0.05
    return 0.1 if round_index < max(1, rounds // 2) else 0.02


def seed_for(bench: Benchmark) -> Strategy:
    sk = bench.skeleton
    return Strategy(
        name=f"seed-{sk.skeleton_id}",
        features=tuple(f"{a}-{b}" for a, b in sk.edges),
        parts=tuple(sk.nodes),
        covered=tuple(sk.required_items),
        confidence=0.6,
        depth=0.7,
    )


@dataclass
class ShardResult:
    skeleton_id: str
    strategy: Strategy
    fitness: float


@dataclass
class ShardedReport:
    shards: list[ShardResult]
    mean_fitness: float
    evaluations: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "mean_fitness": round(self.mean_fitness, 5),
            "evaluations": self.evaluations,
            "shards": [
                {
                    "skeleton": s.skeleton_id,
                    "fitness": round(s.fitness, 5),
                    "strategy": s.strategy.as_dict(),
                }
                for s in self.shards
            ],
        }


def sharded_evolve(
    benchmarks: list[Benchmark],
    cfg: ArenaConfig,
    config: EvolutionConfig,
    mutator: Any | None = None,
) -> ShardedReport:
    shards: list[ShardResult] = []
    evaluations = 0
    for bench in benchmarks:
        report = evolve(
            seed_for(bench),
            [bench],
            cfg,
            EvolutionConfig(
                generations=config.generations,
                population=config.population,
                budget_calls=config.generations * config.population + 10,
                min_delta=config.min_delta,
                seed=config.seed,
                resamples=config.resamples,
                alpha=config.alpha,
            ),
            mutator=mutator,
        )
        evaluations += config.generations * config.population + 1
        if report.best is not None:
            shards.append(
                ShardResult(
                    skeleton_id=bench.skeleton.skeleton_id,
                    strategy=report.best.strategy,
                    fitness=report.best.fitness,
                )
            )
    mean = sum(s.fitness for s in shards) / len(shards) if shards else 0.0
    return ShardedReport(shards=shards, mean_fitness=mean, evaluations=evaluations)


@dataclass
class CombinedReport:
    rounds: int
    best_params: ParamGenome
    sharded: ShardedReport
    single_mean: float
    curve: list[float]
    deltas: Interval | None
    params_history: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "rounds": self.rounds,
            "best_params": self.best_params.as_dict(),
            "sharded": self.sharded.as_dict(),
            "single_mean": round(self.single_mean, 5),
            "curve": [round(x, 5) for x in self.curve],
            "per_benchmark_delta": None
            if self.deltas is None
            else {
                "mean": round(self.deltas.mean, 5),
                "lo": round(self.deltas.lo, 5),
                "hi": round(self.deltas.hi, 5),
                "n": self.deltas.n,
            },
            "params_history": self.params_history,
        }

    def write(self, path: str | Path) -> Path:
        import json

        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return target


def combined_evolve(
    benchmarks: list[Benchmark],
    cfg: ArenaConfig,
    config: EvolutionConfig,
    *,
    rounds: int = 3,
    params_per_round: int = 3,
) -> CombinedReport:
    rng = random.Random(config.seed)
    params = ParamGenome.from_config(cfg)
    sharded = sharded_evolve(benchmarks, params.config(cfg), config)
    best_mean = sharded.mean_fitness
    curve = [best_mean]
    history: list[dict[str, Any]] = []

    for _round in range(rounds):
        improved = False
        scale = anneal_scale(_round, rounds)
        for _ in range(params_per_round):
            candidate = mutate_params(params, rng, scale=scale)
            candidate_sharded = sharded_evolve(benchmarks, candidate.config(cfg), config)
            if candidate_sharded.mean_fitness > best_mean:
                params = candidate
                sharded = candidate_sharded
                best_mean = candidate_sharded.mean_fitness
                improved = True
                history.append({"round": _round, "accepted": True, **candidate.as_dict()})
        if not improved:
            history.append({"round": _round, "accepted": False, "note": "本轮无改进"})
        curve.append(best_mean)

    # 单基因组基线：同一套评估预算，一个策略跨全部基准
    pool = feature_pool(benchmarks)
    nodes = sorted({n for b in benchmarks for n in b.skeleton.nodes})
    single_seed = Strategy(
        name="single",
        features=tuple(pool),
        parts=tuple(nodes),
        covered=tuple(nodes),
        confidence=0.6,
        depth=0.7,
    )
    single_report = evolve(single_seed, benchmarks, params.config(cfg), config)
    single_mean = single_report.best.fitness if single_report.best else 0.0

    deltas: Interval | None = None
    if len(sharded.shards) >= 2:
        per_bench = [
            shard.fitness - single_mean for shard in sharded.shards
        ]
        deltas = paired_bootstrap_ci(per_bench, resamples=config.resamples, seed=0)

    return CombinedReport(
        rounds=rounds,
        best_params=params,
        sharded=sharded,
        single_mean=single_mean,
        curve=curve,
        deltas=deltas,
        params_history=history,
    )


__all__ = [
    "CombinedReport",
    "ParamGenome",
    "ShardResult",
    "ShardedReport",
    "combined_evolve",
    "mutate_params",
    "sharded_evolve",
]
