"""v0.7 增补：LLM 变异器 + 进化 vs 随机搜索对照。

- LlmStrategyMutator：用 complete(prompt)->str 提议新策略，解析失败或越界就退回规则变异；
- random_strategy：同预算下的随机搜索基线；
- compare_search：配对比较「档案进化」与「随机搜索」，给出 CI 与 p 值。

这不是为了证明进化一定更好，而是提供能证伪的对照：如果随机搜索一样好，
档案与选择就没有价值。
"""

from __future__ import annotations

import json
import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from .arena import ArenaConfig
from .evalstats import Interval, bootstrap_pvalue, holm, paired_bootstrap_ci
from .evolution import (
    Benchmark,
    EvolutionConfig,
    Strategy,
    StrategyMutator,
    evolve,
)
from .llm import extract_json


class LlmStrategyMutator:
    """让模型提议变异；输出必须过池子过滤与边界钳制，否则退回规则变异。"""

    def __init__(
        self,
        feature_pool: Sequence[str],
        node_pool: Sequence[str],
        complete: Callable[[str], str],
    ) -> None:
        self.feature_pool = list(feature_pool)
        self.node_pool = list(node_pool)
        self.complete = complete
        self.fallback = StrategyMutator(feature_pool, node_pool)

    def _prompt(self, parent: Strategy) -> str:
        return (
            "你在改进一个多智能体子级策略。只输出 JSON，不要解释。\n"
            f"当前策略：{json.dumps(parent.as_dict(), ensure_ascii=False)}\n"
            f"可选特征：{json.dumps(self.feature_pool, ensure_ascii=False)}\n"
            f"可选节点：{json.dumps(self.node_pool, ensure_ascii=False)}\n"
            '输出格式：{"features": [...], "parts": [...], "covered": [...], '
            '"confidence": 0-1, "depth": 0-1}\n'
            "规则：features 与 parts 只能从给定池子里选；至少保留一个特征；"
            "不要引入池子外的名字。"
        )

    def mutate(self, parent: Strategy, rng: random.Random, name: str) -> Strategy:
        try:
            data = extract_json(self.complete(self._prompt(parent)))
            if not isinstance(data, dict):
                raise ValueError("不是对象")
            features = [f for f in data.get("features", []) if f in self.feature_pool]
            parts = [p for p in data.get("parts", []) if p in self.node_pool]
            covered = [c for c in data.get("covered", []) if c in self.node_pool]
            if not features:
                raise ValueError("特征为空")
            return Strategy(
                name=name,
                features=tuple(sorted(set(features))),
                parts=tuple(sorted(set(parts))) or parent.parts,
                covered=tuple(sorted(set(covered))) or parent.covered,
                confidence=min(0.95, max(0.1, float(data.get("confidence", parent.confidence)))),
                depth=min(0.95, max(0.2, float(data.get("depth", parent.depth)))),
            )
        except Exception:
            return self.fallback.mutate(parent, rng, name)


def random_strategy(
    feature_pool: Sequence[str],
    node_pool: Sequence[str],
    rng: random.Random,
    name: str,
) -> Strategy:
    features = rng.sample(list(feature_pool), k=min(len(feature_pool), rng.randint(1, max(1, len(feature_pool)))))
    parts = rng.sample(list(node_pool), k=min(len(node_pool), rng.randint(1, len(node_pool))))
    covered = rng.sample(list(node_pool), k=min(len(node_pool), rng.randint(0, len(node_pool))))
    return Strategy(
        name=name,
        features=tuple(sorted(set(features))),
        parts=tuple(sorted(set(parts))),
        covered=tuple(sorted(set(covered))),
        confidence=rng.uniform(0.1, 0.95),
        depth=rng.uniform(0.2, 0.95),
    )


def random_search(
    benchmarks: Sequence[Benchmark],
    cfg: ArenaConfig,
    *,
    seed: int,
    evaluations: int,
) -> float:
    """同预算下的随机搜索：返回最高适应度。"""
    from .evolution import evaluate_strategy

    feature_pool = sorted({f for b in benchmarks for f in b.parent.features})
    node_pool = sorted({n for b in benchmarks for n in b.skeleton.nodes})
    rng = random.Random(seed)
    best = 0.0
    for i in range(evaluations):
        strategy = random_strategy(feature_pool, node_pool, rng, f"rand-{i}")
        result = evaluate_strategy(strategy, benchmarks, cfg)
        if result.passed:
            best = max(best, result.fitness)
    return best


@dataclass
class BaselineRow:
    baseline: str
    delta: Interval
    p_value: float
    holm_threshold: float
    significant: bool


@dataclass
class SearchComparison:
    runs: int
    evolution_scores: list[float]
    baseline_scores: dict[str, list[float]]
    rows: list[BaselineRow]

    def as_dict(self) -> dict[str, Any]:
        return {
            "runs": self.runs,
            "evolution_mean": round(sum(self.evolution_scores) / len(self.evolution_scores), 5),
            "baselines": {
                name: round(sum(scores) / len(scores), 5)
                for name, scores in self.baseline_scores.items()
            },
            "rows": [
                {
                    "baseline": row.baseline,
                    "delta": {
                        "mean": round(row.delta.mean, 5),
                        "lo": round(row.delta.lo, 5),
                        "hi": round(row.delta.hi, 5),
                        "n": row.delta.n,
                    },
                    "p_value": round(row.p_value, 4),
                    "holm_threshold": round(row.holm_threshold, 4),
                    "significant": row.significant,
                }
                for row in self.rows
            ],
        }

    def write(self, path: str | Any) -> Any:
        from pathlib import Path

        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return target


def hill_climb(
    seed_strategy: Strategy,
    benchmarks: Sequence[Benchmark],
    cfg: ArenaConfig,
    *,
    seed: int,
    evaluations: int,
) -> float:
    """贪心爬山：只接受比当前更好的变异，不留档案。"""
    from .evolution import evaluate_strategy

    feature_pool = sorted({f for b in benchmarks for f in b.parent.features})
    node_pool = sorted({n for b in benchmarks for n in b.skeleton.nodes})
    rng = random.Random(seed)
    mutator = StrategyMutator(feature_pool, node_pool)
    current = seed_strategy
    best = evaluate_strategy(current, benchmarks, cfg).fitness
    for i in range(evaluations):
        candidate = mutator.mutate(current, rng, f"hc-{i}")
        result = evaluate_strategy(candidate, benchmarks, cfg)
        if result.passed and result.fitness > best:
            best = result.fitness
            current = candidate
    return best


def compare_search(
    seed_strategy: Strategy,
    benchmarks: Sequence[Benchmark],
    cfg: ArenaConfig,
    config: EvolutionConfig | None = None,
    *,
    runs: int = 5,
    resamples: int = 500,
    baselines: Sequence[str] = ("random", "hill"),
    alpha: float = 0.05,
) -> SearchComparison:
    """每轮：进化取最优 vs 各基线取最优（同评估预算），Holm 校正多重比较。"""
    settings = config or EvolutionConfig()
    evaluations = settings.generations * settings.population
    evolution_scores: list[float] = []
    baseline_scores: dict[str, list[float]] = {name: [] for name in baselines}
    for run in range(runs):
        report = evolve(
            seed_strategy,
            benchmarks,
            cfg,
            EvolutionConfig(
                generations=settings.generations,
                population=settings.population,
                budget_calls=settings.budget_calls,
                min_delta=settings.min_delta,
                seed=run,
                resamples=settings.resamples,
                alpha=settings.alpha,
            ),
        )
        evolution_scores.append(report.best.fitness if report.best else 0.0)
        for name in baselines:
            if name == "random":
                score = random_search(benchmarks, cfg, seed=run, evaluations=evaluations)
            elif name == "hill":
                score = hill_climb(
                    seed_strategy, benchmarks, cfg, seed=run, evaluations=evaluations
                )
            else:
                raise ValueError(f"未知基线: {name}")
            baseline_scores[name].append(score)

    pending: list[tuple[str, Interval, float]] = []
    for name in baselines:
        diffs = [e - b for e, b in zip(evolution_scores, baseline_scores[name], strict=False)]
        ci = paired_bootstrap_ci(diffs, resamples=resamples, seed=0)
        p = bootstrap_pvalue(diffs, resamples=resamples, seed=0)
        pending.append((name, ci, p))

    corrected = holm([p for *_, p in pending], alpha=alpha)
    by_index = {idx: (threshold, reject) for idx, threshold, reject in corrected}
    rows = [
        BaselineRow(
            baseline=name,
            delta=ci,
            p_value=p,
            holm_threshold=by_index[i][0],
            significant=by_index[i][1],
        )
        for i, (name, ci, p) in enumerate(pending)
    ]
    return SearchComparison(
        runs=runs,
        evolution_scores=evolution_scores,
        baseline_scores=baseline_scores,
        rows=rows,
    )


__all__ = [
    "BaselineRow",
    "LlmStrategyMutator",
    "SearchComparison",
    "compare_search",
    "hill_climb",
    "random_search",
    "random_strategy",
]
