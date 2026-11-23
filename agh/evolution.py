"""自我迭代：档案式进化（DGM / AlphaEvolve 的最小可用版）。

思路不是「让模型改自己的代码」，而是把可进化的对象收窄成一个**受限基因组**：
子级策略（特征集合、覆盖、置信、垂直深度）。这样有三条好处：

1. 变异有边界：任何基因组都落在允许范围内，不会进化出越权行为；
2. 评估用现成的竞技场：同一套骨架基准，分数就是适应度；
3. 接受要过治理：候选策略必须走 VALIDATING → VERIFIED，且分数不能倒退。

档案保留所有变体（不只最好的），按「分数 + 新颖度」锦标赛选择父代，
血统可追溯。参考：DGM（arXiv 2505.22954）、AlphaEvolve（arXiv 2506.13131）、
自进化智能体综述（arXiv 2507.21046）；失败模式「misevolve」见 arXiv 2509.26354，
对应的防线是基因组边界 + 冻结配置 + 治理门。

v0.1 的适应度是规则子级下的竞技场分数：它验证机制，不代表真实模型能力。
"""

from __future__ import annotations

import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .arena import ArenaConfig, hard_filter, score_candidate
from .contracts import (
    AbstractSignature,
    BudgetVector,
    CoverageClaim,
    GestaltReconstruction,
    Skeleton,
)
from .eventlog import EventLog, LogTampered
from .governance import GovernanceMachine
from .ledger import BudgetExceeded, Ledger


@dataclass(frozen=True)
class Strategy:
    """可进化的子级策略。"""

    name: str
    features: tuple[str, ...]
    parts: tuple[str, ...]
    covered: tuple[str, ...]
    confidence: float = 0.6
    depth: float = 0.7

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "features": list(self.features),
            "parts": list(self.parts),
            "covered": list(self.covered),
            "confidence": self.confidence,
            "depth": self.depth,
        }


@dataclass(frozen=True)
class Benchmark:
    skeleton: Skeleton
    parent: AbstractSignature


@dataclass
class EvalResult:
    fitness: float
    scores: list[float]
    passed: bool
    notes: list[str] = field(default_factory=list)


@dataclass
class Variant:
    variant_id: str
    parent_id: str | None
    generation: int
    strategy: Strategy
    fitness: float
    scores: list[float]
    accepted: bool
    novelty: float = 0.0


def strategy_child(strategy: Strategy, skeleton: Skeleton) -> Callable[[str], GestaltReconstruction]:
    def build(contract_id: str) -> GestaltReconstruction:
        return GestaltReconstruction(
            child_id=strategy.name,
            contract_id=contract_id,
            skeleton_id=skeleton.skeleton_id,
            parts=list(strategy.parts),
            coverage=CoverageClaim(covered=list(strategy.covered)),
            signature=AbstractSignature(
                signature_id=f"sig-{strategy.name}", features=list(strategy.features)
            ),
            self_confidence=strategy.confidence,
            content={
                "edges": [list(e) for e in skeleton.edges],
                "vertical_moves": [
                    {"node": m.node, "declared_depth": m.declared_depth, "preserved_depth": strategy.depth}
                    for m in skeleton.moves
                    if m.vertical
                ],
                "changed_nodes": [],
            },
        )

    return build


def evaluate_strategy(
    strategy: Strategy,
    benchmarks: Sequence[Benchmark],
    cfg: ArenaConfig,
) -> EvalResult:
    scores: list[float] = []
    notes: list[str] = []
    passed = True
    for bench in benchmarks:
        recon = strategy_child(strategy, bench.skeleton)("ct-evolve")
        filt = hard_filter(recon, bench.skeleton)
        if not filt.passed:
            passed = False
            notes.append(f"{bench.skeleton.skeleton_id}: 硬过滤拒收 {filt.reasons}")
            scores.append(0.0)
            continue
        breakdown = score_candidate(
            recon, bench.skeleton, cfg, verifier_score=None, parent_signature=bench.parent
        )
        scores.append(breakdown.score)
    fitness = sum(scores) / len(scores) if scores else 0.0
    return EvalResult(fitness=fitness, scores=scores, passed=passed, notes=notes)


class StrategyMutator:
    """有边界的随机变异：只在给定池子里增删特征、覆盖与数值。"""

    def __init__(self, feature_pool: Sequence[str], node_pool: Sequence[str]) -> None:
        self.feature_pool = list(feature_pool)
        self.node_pool = list(node_pool)

    def mutate(self, parent: Strategy, rng: random.Random, name: str) -> Strategy:
        features = set(parent.features)
        parts = set(parent.parts)
        covered = set(parent.covered)
        confidence = parent.confidence
        depth = parent.depth

        for _ in range(rng.randint(1, 3)):
            action = rng.choice(["add_feature", "drop_feature", "add_part", "add_cover", "conf", "depth"])
            if action == "add_feature" and self.feature_pool:
                features.add(rng.choice(self.feature_pool))
            elif action == "drop_feature" and len(features) > 1:
                features.discard(rng.choice(sorted(features)))
            elif action == "add_part" and self.node_pool:
                parts.add(rng.choice(self.node_pool))
            elif action == "add_cover" and self.node_pool:
                covered.add(rng.choice(self.node_pool))
            elif action == "conf":
                confidence = min(0.95, max(0.1, confidence + rng.choice([-0.1, 0.1])))
            elif action == "depth":
                depth = min(0.95, max(0.2, depth + rng.choice([-0.1, 0.1])))

        return Strategy(
            name=name,
            features=tuple(sorted(features)),
            parts=tuple(sorted(parts)),
            covered=tuple(sorted(covered)),
            confidence=confidence,
            depth=depth,
        )


class Archive:
    """保留所有变体（不只最优），按分数与新颖度选择父代。"""

    def __init__(self) -> None:
        self._variants: list[Variant] = []

    def add(self, variant: Variant) -> None:
        self._variants.append(variant)

    def all(self) -> list[Variant]:
        return list(self._variants)

    def size(self) -> int:
        return len(self._variants)

    def best(self) -> Variant | None:
        if not self._variants:
            return None
        return max(self._variants, key=lambda v: (v.fitness, v.novelty))

    def select(self, rng: random.Random, k: int = 3) -> Variant:
        if not self._variants:
            raise ValueError("档案为空")
        sample = rng.sample(self._variants, min(k, len(self._variants)))
        return max(sample, key=lambda v: (v.fitness + 0.2 * v.novelty, v.fitness))


def novelty_of(strategy: Strategy, archive: Sequence[Variant]) -> float:
    if not archive:
        return 1.0
    mine = set(strategy.features)
    distances = []
    for variant in archive:
        other = set(variant.strategy.features)
        union = mine | other
        distances.append(1.0 - (len(mine & other) / len(union)) if union else 0.0)
    return sum(distances) / len(distances)


@dataclass
class EvolutionConfig:
    generations: int = 5
    population: int = 3
    budget_calls: int = 500
    min_delta: float = 0.0
    seed: int = 7
    resamples: int = 500
    alpha: float = 0.05


@dataclass
class EvolutionReport:
    generations: int
    accepted: int
    best: Variant | None
    archive_size: int
    curve: list[float]
    lineage: list[dict[str, Any]]
    budget: dict[str, Any]
    governance_state: str
    notes: list[str] = field(default_factory=list)
    log_entries: int = 0
    log_ok: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "generations": self.generations,
            "accepted": self.accepted,
            "archive_size": self.archive_size,
            "curve": [round(x, 5) for x in self.curve],
            "budget": self.budget,
            "governance_state": self.governance_state,
            "best": {
                "id": self.best.variant_id,
                "fitness": round(self.best.fitness, 5),
                "strategy": self.best.strategy.as_dict(),
            }
            if self.best
            else None,
            "lineage": self.lineage,
            "notes": self.notes,
            "log_entries": self.log_entries,
            "log_ok": self.log_ok,
        }

    def write(self, path: str | Path) -> Path:
        import json

        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return target


def _budget_dict(ledger: Ledger) -> dict[str, Any]:
    snap = ledger.snapshot()
    return {
        "committed": snap.committed.model_dump(),
        "outstanding": snap.outstanding.model_dump(),
        "available": snap.available.model_dump(),
        "active_leases": snap.active_leases,
        "violations": snap.violations,
    }


def evolve(
    seed_strategy: Strategy,
    benchmarks: Sequence[Benchmark],
    cfg: ArenaConfig,
    config: EvolutionConfig | None = None,
    log: EventLog | None = None,
    mutator: Any | None = None,
) -> EvolutionReport:
    """档案式进化主循环：变异 → 评估 → 接受/拒绝 → 入档。"""
    settings = config or EvolutionConfig()
    if not benchmarks:
        raise ValueError("至少需要一个基准")
    rng = random.Random(settings.seed)
    ledger = Ledger(
        BudgetVector(compute_units=settings.budget_calls, wall_ms=settings.budget_calls * 1000, usd=1.0)
    )
    governance = GovernanceMachine(frozen=None)
    governance.transition("VALIDATING", tier="T1")

    feature_pool = sorted({f for b in benchmarks for f in b.parent.features})
    node_pool = sorted({n for b in benchmarks for n in b.skeleton.nodes})
    active_mutator = mutator if mutator is not None else StrategyMutator(feature_pool, node_pool)
    archive = Archive()
    notes: list[str] = []

    def record(kind: str, payload: dict[str, Any]) -> None:
        if log is not None:
            log.append(kind, payload)

    seed_eval = evaluate_strategy(seed_strategy, benchmarks, cfg)
    record("evolution.start", {"seed": seed_strategy.name, "fitness": seed_eval.fitness})
    seed_variant = Variant(
        variant_id="v0-seed",
        parent_id=None,
        generation=0,
        strategy=seed_strategy,
        fitness=seed_eval.fitness,
        scores=seed_eval.scores,
        accepted=True,
        novelty=1.0,
    )
    archive.add(seed_variant)
    curve = [seed_eval.fitness]
    accepted = 1
    lineage: list[dict[str, Any]] = [
        {"id": seed_variant.variant_id, "parent": None, "fitness": round(seed_eval.fitness, 5)}
    ]

    counter = 1
    try:
        for generation in range(1, settings.generations + 1):
            generation_best = curve[-1]
            for _ in range(settings.population):
                parent = archive.select(rng)
                child_strategy = active_mutator.mutate(parent.strategy, rng, f"v{counter}-g{generation}")
                lease = ledger.reserve(
                    owner=child_strategy.name,
                    reserved=BudgetVector(compute_units=1, wall_ms=1000, usd=0.01),
                    max_tokens=1,
                )
                result = evaluate_strategy(child_strategy, benchmarks, cfg)
                ledger.settle(lease.lease_id, BudgetVector(compute_units=1, wall_ms=1000, usd=0.01))
                novelty = novelty_of(child_strategy, archive.all())

                # 接受条件：适应度不倒退，且（有提升或明显更新颖）
                improved = result.fitness > parent.fitness + settings.min_delta
                accept = result.passed and (
                    improved or (result.fitness >= parent.fitness and novelty > 0.5)
                )
                variant = Variant(
                    variant_id=child_strategy.name,
                    parent_id=parent.variant_id,
                    generation=generation,
                    strategy=child_strategy,
                    fitness=result.fitness,
                    scores=result.scores,
                    accepted=accept,
                    novelty=novelty,
                )
                archive.add(variant)
                record(
                    "evolution.mutation",
                    {
                        "id": variant.variant_id,
                        "parent": parent.variant_id,
                        "fitness": result.fitness,
                        "accepted": accept,
                        "novelty": novelty,
                    },
                )
                lineage.append(
                    {
                        "id": variant.variant_id,
                        "parent": parent.variant_id,
                        "fitness": round(result.fitness, 5),
                        "accepted": accept,
                        "novelty": round(novelty, 3),
                    }
                )
                if accept:
                    accepted += 1
                    generation_best = max(generation_best, result.fitness)
                counter += 1
            curve.append(generation_best)

        best = archive.best()
        record(
            "evolution.end",
            {
                "accepted": accepted,
                "archive_size": archive.size(),
                "best": best.variant_id if best else None,
                "best_fitness": best.fitness if best else 0.0,
            },
        )
        # 治理：最优变体进入 VERIFIED（T1，无需人工）
        governance.transition("VERIFIED", tier="T1", reason="进化接受")
        return EvolutionReport(
            generations=settings.generations,
            accepted=accepted,
            best=best,
            archive_size=archive.size(),
            curve=curve,
            lineage=lineage,
            budget=_budget_dict(ledger),
            governance_state=governance.state,
            notes=notes,
            log_entries=len(log.read()) if log is not None else 0,
            log_ok=_log_ok(log),
        )
    except BudgetExceeded as exc:
        notes.append(f"预算耗尽，提前停止：{exc}")
        return EvolutionReport(
            generations=len(curve) - 1,
            accepted=accepted,
            best=archive.best(),
            archive_size=archive.size(),
            curve=curve,
            lineage=lineage,
            budget=_budget_dict(ledger),
            governance_state=governance.state,
            notes=notes,
            log_entries=len(log.read()) if log is not None else 0,
            log_ok=_log_ok(log),
        )


def _log_ok(log: EventLog | None) -> bool:
    if log is None:
        return True
    try:
        log.verify()
        return True
    except LogTampered:
        return False


def default_benchmarks(skeleton: Skeleton, parent_features: Sequence[str]) -> list[Benchmark]:
    """默认基准：原骨架 + 两个变体（少一条边 / 多一个必需项）。"""
    base = Benchmark(skeleton=skeleton, parent=AbstractSignature(signature_id="p-base", features=list(parent_features)))
    deep = skeleton.model_copy(
        update={
            "skeleton_id": f"{skeleton.skeleton_id}-deep",
            "required_items": list(dict.fromkeys([*skeleton.required_items, skeleton.nodes[-1]])),
        }
    )
    wide = skeleton.model_copy(
        update={
            "skeleton_id": f"{skeleton.skeleton_id}-wide",
            "edges": [*skeleton.edges, (skeleton.edges[0][0], skeleton.nodes[-1])],
        }
    )
    return [
        base,
        Benchmark(skeleton=deep, parent=base.parent),
        Benchmark(skeleton=wide, parent=base.parent),
    ]


__all__ = [
    "Archive",
    "Benchmark",
    "EvolutionConfig",
    "EvolutionReport",
    "Strategy",
    "StrategyMutator",
    "Variant",
    "default_benchmarks",
    "evaluate_strategy",
    "evolve",
    "strategy_child",
]
