"""元进化：让系统学会「怎么改自己」，并自己加难度。

两步，都在安全边界内：
1. **算子学习**：参数变异拆成几种算子（加权重、减权重、换权重、调 τ），
   用 UCB1 多臂老虎机按「是否带来改进」给算子记功，越有用的算子被选得越多；
2. **课程**：连续若干轮没有改进就把基准难度抬一档（更多节点、更多边、更高必需项比例），
   在更难的基准上继续进化。

这不是代码级自改，进化对象仍是参数与策略；AGI 谈不上，但「自我改进」的闭环
（评估 → 归因 → 调整搜索策略 → 提高目标）是完整的。
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .arena import ArenaConfig
from .benchmarks import generate_benchmarks
from .evolution import EvolutionConfig
from .evolution_sharded import (
    ParamGenome,
    ShardedReport,
    anneal_scale,
    normalize_weights,
    sharded_evolve,
)

OPERATORS = ("weight_up", "weight_down", "weight_swap", "tau_up", "tau_down")


class OperatorBandit:
    """UCB1：未试过的算子先试，之后按均值 + 置信上界选。"""

    def __init__(self, operators: tuple[str, ...] = OPERATORS, c: float = 0.7) -> None:
        self.operators = operators
        self.c = c
        self.counts = dict.fromkeys(operators, 0)
        self.rewards = dict.fromkeys(operators, 0.0)
        self.total = 0

    def choose(self, rng: random.Random) -> str:
        for op in self.operators:
            if self.counts[op] == 0:
                return op
        best_op = self.operators[0]
        best_value = -1.0
        for op in self.operators:
            mean = self.rewards[op] / self.counts[op]
            bonus = self.c * math.sqrt(math.log(self.total + 1) / self.counts[op])
            value = mean + bonus
            if value > best_value:
                best_value = value
                best_op = op
        return best_op

    def update(self, op: str, reward: float) -> None:
        self.counts[op] += 1
        self.rewards[op] += reward
        self.total += 1

    def stats(self) -> dict[str, dict[str, float]]:
        return {
            op: {
                "n": self.counts[op],
                "mean_reward": round(self.rewards[op] / self.counts[op], 3) if self.counts[op] else 0.0,
            }
            for op in self.operators
        }


def apply_operator(
    genome: ParamGenome, op: str, rng: random.Random, scale: float
) -> ParamGenome:
    weights = dict(genome.weights)
    keys = sorted(weights)
    tau = genome.dissent_tau
    if op in ("weight_up", "weight_down"):
        key = rng.choice(keys)
        delta = scale * (1 if op == "weight_up" else -1)
        weights[key] = min(1.0, max(0.0, weights[key] + delta))
    elif op == "weight_swap":
        a, b = rng.sample(keys, 2)
        weights[a], weights[b] = weights[b], weights[a]
    elif op == "tau_up":
        tau = min(0.9, tau + scale)
    elif op == "tau_down":
        tau = max(0.05, tau - scale)
    else:
        raise ValueError(f"未知算子: {op}")
    return ParamGenome(weights=normalize_weights(weights), dissent_tau=round(tau, 3))


def curriculum_benchmarks(level: int, seed: int):
    """难度随等级上升：节点更多、边更密、必需项更多。"""
    nodes = min(9, 4 + level)
    return generate_benchmarks(
        6,
        seed=seed + level,
        min_nodes=nodes,
        max_nodes=nodes,
        extra_edges=1 + level,
        required_ratio=min(0.7, 0.4 + 0.05 * level),
    )


@dataclass
class MetaReport:
    rounds: int
    curve: list[float]
    levels: list[int]
    best_params: ParamGenome
    final_sharded: ShardedReport
    bandit: dict[str, dict[str, float]] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "rounds": self.rounds,
            "curve": [round(x, 5) for x in self.curve],
            "levels": self.levels,
            "best_params": self.best_params.as_dict(),
            "final_mean": round(self.final_sharded.mean_fitness, 5),
            "bandit": self.bandit,
            "events": self.events,
        }

    def write(self, path: str | Path) -> Path:
        import json

        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return target


def meta_evolve(
    cfg: ArenaConfig,
    config: EvolutionConfig,
    *,
    rounds: int = 8,
    seed: int = 0,
    patience: int = 2,
) -> MetaReport:
    rng = random.Random(seed)
    bandit = OperatorBandit()
    params = ParamGenome.from_config(cfg)
    level = 1
    benchmarks = curriculum_benchmarks(level, seed)
    sharded = sharded_evolve(benchmarks, params.config(cfg), config)
    best = sharded.mean_fitness
    curve = [best]
    levels = [level]
    events: list[dict[str, Any]] = []
    stale = 0

    for round_index in range(rounds):
        op = bandit.choose(rng)
        scale = anneal_scale(round_index, rounds)
        candidate = apply_operator(params, op, rng, scale)
        candidate_sharded = sharded_evolve(benchmarks, candidate.config(cfg), config)
        improved = candidate_sharded.mean_fitness > best
        bandit.update(op, 1.0 if improved else 0.0)
        events.append(
            {
                "round": round_index,
                "op": op,
                "improved": improved,
                "mean": round(candidate_sharded.mean_fitness, 5),
                "level": level,
            }
        )
        if improved:
            params = candidate
            sharded = candidate_sharded
            best = candidate_sharded.mean_fitness
            stale = 0
        else:
            stale += 1
        if stale >= patience and level < 5:
            level += 1
            benchmarks = curriculum_benchmarks(level, seed)
            sharded = sharded_evolve(benchmarks, params.config(cfg), config)
            best = sharded.mean_fitness
            stale = 0
            events.append({"round": round_index, "op": "curriculum", "level": level, "mean": round(best, 5)})
        curve.append(best)
        levels.append(level)

    return MetaReport(
        rounds=rounds,
        curve=curve,
        levels=levels,
        best_params=params,
        final_sharded=sharded,
        bandit=bandit.stats(),
        events=events,
    )


__all__ = [
    "OPERATORS",
    "MetaReport",
    "OperatorBandit",
    "apply_operator",
    "curriculum_benchmarks",
    "meta_evolve",
]
