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
            weights=normalize_weights(dict(self.weights)),
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
    return ParamGenome(weights=normalize_weights(weights), dissent_tau=tau)


def normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    """归一化到和为 1：否则权重整体变大也会抬高分数，改进是假的。"""
    clamped = {k: max(0.0, float(v)) for k, v in weights.items()}
    total = sum(clamped.values())
    if total <= 0:
        return weights
    scaled = {k: round(v / total, 4) for k, v in clamped.items()}
    # 四舍五入后补齐到 1，补在最大的那一项上
    diff = round(1.0 - sum(scaled.values()), 4)
    if diff:
        key = max(scaled, key=lambda k: scaled[k])
        scaled[key] = round(scaled[key] + diff, 4)
    return scaled


def anneal_scale(round_index: int, rounds: int) -> float:
    """前半程粗搜（0.1），后半程细搜（0.02）。"""
    if rounds <= 1:
        return 0.05
    return 0.1 if round_index < max(1, rounds // 2) else 0.02


def visible_pool_for(bench: Benchmark, *, degrade: float, seed: int) -> list[str]:
    """信息降质：变异器只看得到降质后仍保留的边，缺的边得靠推断补。"""
    if degrade <= 0:
        return sorted(f"{a}-{b}" for a, b in bench.skeleton.edges)
    degraded = seed_for(
        bench,
        degrade=degrade,
        rng=random.Random(f"{seed}:{bench.skeleton.skeleton_id}"),
    )
    return sorted(degraded.features)


def seed_for(
    bench: Benchmark,
    *,
    degrade: float = 0.0,
    rng: random.Random | None = None,
) -> Strategy:
    """种子策略。

    degrade > 0 时随机抽掉一部分边特征与必需项：全集种子是适应度上界，
    搜索没有梯度；降质后进化才有「补回来」的空间。降质必须确定（给定 rng），
    否则同一参数候选每次评估的种子都不同，比较失去意义。
    """
    sk = bench.skeleton
    features = [f"{a}-{b}" for a, b in sk.edges]
    covered = list(sk.required_items)
    if degrade > 0 and rng is not None:
        keep_f = max(1, round(len(features) * (1.0 - degrade)))
        keep_c = max(1, round(len(covered) * (1.0 - degrade)))
        rng.shuffle(features)
        rng.shuffle(covered)
        features = sorted(features[:keep_f])
        covered = sorted(covered[:keep_c])
    return Strategy(
        name=f"seed-{sk.skeleton_id}",
        features=tuple(features),
        parts=tuple(sk.nodes),
        covered=tuple(covered),
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


_SHARD_CACHE: dict[tuple, tuple[float, Strategy]] = {}
_SHARD_CACHE_MAX = 256


def _cache_put(key: tuple, value: tuple[float, Strategy]) -> None:
    """有界缓存：daemon 长跑时键随参数/种子变化，不设上限会一直涨。"""
    _SHARD_CACHE[key] = value
    while len(_SHARD_CACHE) > _SHARD_CACHE_MAX:
        _SHARD_CACHE.pop(next(iter(_SHARD_CACHE)))


def sharded_evolve(
    benchmarks: list[Benchmark],
    cfg: ArenaConfig,
    config: EvolutionConfig,
    mutator: Any | None = None,
    verifier: Any | None = None,
    *,
    seed_degrade: float = 0.0,
    carry: dict[str, Strategy] | None = None,
    hide_gold: bool = False,
    mutator_factory: Any | None = None,
) -> ShardedReport:
    """carry: 上一轮的每基准精英，作为本轮起点。

    跨轮精英延续是「持续改进」的前提：每轮都从同一个降质种子重跑，
    结果确定，曲线只能是水平线。
    """
    shards: list[ShardResult] = []
    evaluations = 0
    for bench in benchmarks:
        carried = carry.get(bench.skeleton.skeleton_id) if carry else None
        bench_seed = carried or seed_for(
            bench,
            degrade=seed_degrade,
            rng=random.Random(f"{config.seed}:{bench.skeleton.skeleton_id}"),
        )
        bench_mutator = mutator
        if mutator_factory is not None:
            bench_mutator = mutator_factory(
                visible_pool_for(bench, degrade=seed_degrade, seed=config.seed)
                if hide_gold
                else sorted(f"{a}-{b}" for a, b in bench.skeleton.edges),
                sorted(bench.skeleton.nodes),
            )
        pool = (
            visible_pool_for(bench, degrade=seed_degrade, seed=config.seed)
            if hide_gold
            else None
        )
        key = None
        if bench_mutator is None:
            key = (
                bench.skeleton.skeleton_id,
                tuple(bench_seed.features),
                tuple(bench_seed.covered),
                tuple(pool) if pool is not None else (),
                tuple(sorted(cfg.weights.items())),
                cfg.dissent_tau,
                config.generations,
                config.population,
                config.seed,
                type(verifier).__name__ if verifier is not None else "",
            )
            if key in _SHARD_CACHE:
                evaluations += config.generations * config.population + 1
                cached_fitness, cached_strategy = _SHARD_CACHE[key]
                shards.append(
                    ShardResult(
                        skeleton_id=bench.skeleton.skeleton_id,
                        strategy=cached_strategy,
                        fitness=cached_fitness,
                    )
                )
                continue
        report = evolve(
            bench_seed,
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
            mutator=bench_mutator,
            verifier=verifier,
            feature_pool=pool,
        )
        evaluations += config.generations * config.population + 1
        if key is not None and report.best is not None:
            _cache_put(key, (report.best.fitness, report.best.strategy))
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
    objective: float | None = None
    carry: dict[str, Strategy] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "rounds": self.rounds,
            "best_params": self.best_params.as_dict(),
            "sharded": self.sharded.as_dict(),
            "single_mean": round(self.single_mean, 5),
            "objective": None if self.objective is None else round(self.objective, 5),
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


def single_seed_features(
    benchmarks: list[Benchmark],
    *,
    degrade: float = 0.0,
    seed: int = 0,
) -> list[str]:
    """单基因组基线的特征集：降质时取各分片降质种子的并集，保持同等信息预算。"""
    if degrade <= 0:
        return feature_pool(benchmarks)
    feats: set[str] = set()
    for bench in benchmarks:
        degraded = seed_for(
            bench,
            degrade=degrade,
            rng=random.Random(f"{seed}:{bench.skeleton.skeleton_id}"),
        )
        feats.update(degraded.features)
    return sorted(feats)


def combined_evolve(
    benchmarks: list[Benchmark],
    cfg: ArenaConfig,
    config: EvolutionConfig,
    *,
    rounds: int = 3,
    params_per_round: int = 3,
    mutator: Any | None = None,
    verifier: Any | None = None,
    reference_cfg: ArenaConfig | None = None,
    seed_degrade: float = 0.0,
    carry: dict[str, Strategy] | None = None,
    hide_gold: bool = False,
    mutator_factory: Any | None = None,
) -> CombinedReport:
    """分片精英 + 参数进化。

    reference_cfg 非空时，参数候选的取舍改用「固定参照权重」重打分：
    否则被搜索的权重就是打分函数本身，最优解必然是把惩罚项权重压到下界，
    那是换尺子，不是改进。
    """
    from .evolution import evaluate_strategy

    rng = random.Random(config.seed)
    bench_by_id = {b.skeleton.skeleton_id: b for b in benchmarks}

    def objective(sharded_report: ShardedReport) -> float:
        if reference_cfg is None or verifier is None:
            return sharded_report.mean_fitness
        scores = [
            evaluate_strategy(
                shard.strategy, [bench_by_id[shard.skeleton_id]], reference_cfg, verifier=verifier
            ).fitness
            for shard in sharded_report.shards
            if shard.skeleton_id in bench_by_id
        ]
        return sum(scores) / len(scores) if scores else 0.0

    params = ParamGenome.from_config(cfg)
    sharded = sharded_evolve(
        benchmarks,
        params.config(cfg),
        config,
        mutator=mutator,
        verifier=verifier,
        seed_degrade=seed_degrade,
        carry=carry,
        hide_gold=hide_gold,
        mutator_factory=mutator_factory,
    )
    best_mean = objective(sharded)
    curve = [best_mean]
    history: list[dict[str, Any]] = []

    for _round in range(rounds):
        improved = False
        scale = anneal_scale(_round, rounds)
        for _ in range(params_per_round):
            candidate = mutate_params(params, rng, scale=scale)
            candidate_sharded = sharded_evolve(
                benchmarks,
                candidate.config(cfg),
                config,
                verifier=verifier,
                seed_degrade=seed_degrade,
                carry=carry,
                hide_gold=hide_gold,
            )
            score = objective(candidate_sharded)
            if score > best_mean:
                params = candidate
                sharded = candidate_sharded
                best_mean = score
                improved = True
                history.append({"round": _round, "accepted": True, **candidate.as_dict()})
        if not improved:
            history.append({"round": _round, "accepted": False, "note": "本轮无改进"})
        curve.append(best_mean)

    # 单基因组基线：同一套评估预算，一个策略跨全部基准。
    # 降质时必须用同一信息预算：否则基线拿到全集、分片只拿到降质子集，
    # 两者的差值就不是「分片 vs 单基因组」，而是「信息多 vs 信息少」。
    pool = single_seed_features(benchmarks, degrade=seed_degrade, seed=config.seed)
    nodes = sorted({n for b in benchmarks for n in b.skeleton.nodes})
    single_seed = Strategy(
        name="single",
        features=tuple(pool),
        parts=tuple(nodes),
        covered=tuple(nodes),
        confidence=0.6,
        depth=0.7,
    )
    single_report = evolve(single_seed, benchmarks, params.config(cfg), config, verifier=verifier)
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
        objective=best_mean,
        carry={s.skeleton_id: s.strategy for s in sharded.shards},
    )


__all__ = [
    "CombinedReport",
    "ParamGenome",
    "ShardResult",
    "ShardedReport",
    "combined_evolve",
    "mutate_params",
    "seed_for",
    "sharded_evolve",
    "single_seed_features",
]
