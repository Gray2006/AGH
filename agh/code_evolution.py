"""以真实测试通过率为适应度的求解策略进化，并与随机搜索做配对对照。

与 `agh/evolution.py` 的区别：那边的适应度来自 AGH 自己定义的结构规则；这里适应度来自
**在子进程里真跑 hidden 测试**，对错不由 AGH 决定。

防过拟合：任务分 train / held-out。进化只看 train；最终比较只在 held-out 上做，
并用配对 bootstrap 给出置信区间。held-out 只有几题时，区间会很宽，这是如实的不确定性。

预算：以「模型调用次数」计。进化与随机搜索使用同样的调用预算，否则比较的是预算不是方法。
"""

from __future__ import annotations

import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from .codesolve import (
    HINT_CHOICES,
    N_SAMPLES_CHOICES,
    ROUND_CHOICES,
    SELECT_CHOICES,
    SolverPolicy,
    solve_task,
)
from .codetasks import CodeTask
from .evalstats import Interval, paired_bootstrap_ci


@dataclass(frozen=True)
class PolicyEval:
    policy: SolverPolicy
    per_task: tuple[float, ...]  # 每题 hidden 得分，顺序同 tasks
    calls: int
    lam: float
    call_errors: int = 0
    # 相对「评估前的最好分数」的增量。Oudeyer 的学习进步假设：内在奖励应是
    # 误差的下降，而不是绝对水平或新奇度。
    progress: float = 0.0

    @property
    def score(self) -> float:
        return sum(self.per_task) / len(self.per_task)

    @property
    def fitness(self) -> float:
        """得分减去调用成本；lam=0 时只看得分（会倾向最大采样数）。"""
        return self.score - self.lam * (self.calls / len(self.per_task))


def evaluate_policy(
    policy: SolverPolicy, tasks: Sequence[CodeTask], complete: Callable[[str], str], lam: float = 0.01
) -> PolicyEval:
    outs = [solve_task(t, complete, policy) for t in tasks]
    return PolicyEval(
        policy,
        tuple(o.hidden_score for o in outs),
        sum(o.calls for o in outs),
        lam,
        sum(o.call_errors for o in outs),
    )


def mutate(policy: SolverPolicy, rng: random.Random) -> SolverPolicy:
    gene = rng.choice(("n_samples", "select", "hint"))
    if gene == "n_samples":
        i = N_SAMPLES_CHOICES.index(policy.n_samples)
        j = max(0, min(len(N_SAMPLES_CHOICES) - 1, i + rng.choice((-1, 1))))
        return SolverPolicy(N_SAMPLES_CHOICES[j], policy.select, policy.hint, policy.rounds)
    if gene == "select":
        return SolverPolicy(
            policy.n_samples, rng.choice(SELECT_CHOICES), policy.hint, policy.rounds
        )
    if gene == "rounds":
        return SolverPolicy(
            policy.n_samples, policy.select, policy.hint, rng.choice(ROUND_CHOICES)
        )
    return SolverPolicy(
        policy.n_samples, policy.select, rng.choice(HINT_CHOICES), policy.rounds
    )


def random_policy(rng: random.Random) -> SolverPolicy:
    return SolverPolicy(
        rng.choice(N_SAMPLES_CHOICES),
        rng.choice(SELECT_CHOICES),
        rng.choice(HINT_CHOICES),
        rng.choice(ROUND_CHOICES),
    )


@dataclass
class SearchResult:
    method: str
    best: PolicyEval
    evaluations: int
    calls_spent: int
    history: list[tuple[str, float]] = field(default_factory=list)  # (policy key, fitness)


def _search(
    method: str,
    propose: Callable[[list[PolicyEval], random.Random], SolverPolicy],
    train: Sequence[CodeTask],
    complete: Callable[[str], str],
    call_budget: int,
    seed: int,
    lam: float,
    start: SolverPolicy,
    reward: str = "absolute",
) -> SearchResult:
    rng = random.Random(seed)
    cache: dict[str, PolicyEval] = {}
    archive: list[PolicyEval] = []
    spent = 0
    history: list[tuple[str, float]] = []
    candidate = start
    attempts = 0
    while attempts < 10_000:  # 防御：策略空间很小，缓存命中不花预算，要靠 attempts 兜底
        attempts += 1
        key = candidate.key()
        if key not in cache:
            cost = candidate.n_samples * len(train)
            # 预算软上限：至少评估一个候选，否则调用预算小于单次成本时无从比较
            if archive and spent + cost > call_budget:
                break
            ev = evaluate_policy(candidate, train, complete, lam)
            cache[key] = ev
            best_before = max((e.fitness for e in archive), default=0.0)
            ev = replace(ev, progress=ev.fitness - best_before)
            archive.append(ev)
            spent += ev.calls
            history.append((key, ev.fitness))
        candidate = propose(archive, rng)
    if not archive:
        raise ValueError(f"调用预算 {call_budget} 连一个候选都跑不完（train={len(train)} 题）")
    best = max(archive, key=lambda e: e.fitness)
    return SearchResult(method, best, len(archive), spent, history)


def _pick_parent(archive: list[PolicyEval], rng: random.Random, reward: str) -> PolicyEval:
    """3 选 1 锦标赛。progress 模式选「进步最大」的，而不是「分数最高」的：
    分数最高的往往已到局部最优，继续变异只会退化。"""
    pool = rng.sample(archive, min(3, len(archive)))
    if reward == "progress":
        return max(pool, key=lambda e: (e.progress, e.fitness))
    return max(pool, key=lambda e: e.fitness)


def _make_evolve_propose(reward: str):
    def propose(archive: list[PolicyEval], rng: random.Random) -> SolverPolicy:
        return mutate(_pick_parent(archive, rng, reward).policy, rng)

    return propose


def _random_propose(_archive: list[PolicyEval], rng: random.Random) -> SolverPolicy:
    return random_policy(rng)


def evolve_policy(
    train, complete, call_budget, seed=0, lam=0.01, start=None, reward="absolute"
) -> SearchResult:
    return _search(
        "evolution",
        _make_evolve_propose(reward),
        train,
        complete,
        call_budget,
        seed,
        lam,
        start or SolverPolicy(),
        reward,
    )


def random_search(
    train, complete, call_budget, seed=0, lam=0.01, reward="absolute"
) -> SearchResult:
    start = random_policy(random.Random(seed))
    return _search(
        "random", _random_propose, train, complete, call_budget, seed, lam, start, reward
    )


def split_tasks(tasks: Sequence[CodeTask], held_out: int, seed: int = 0) -> tuple[list[CodeTask], list[CodeTask]]:
    ids = sorted(range(len(tasks)))
    random.Random(seed).shuffle(ids)
    test_idx = set(ids[:held_out])
    train = [t for i, t in enumerate(tasks) if i not in test_idx]
    test = [t for i, t in enumerate(tasks) if i in test_idx]
    return train, test


@dataclass(frozen=True)
class Comparison:
    name: str
    interval: Interval

    def as_dict(self) -> dict[str, Any]:
        i = self.interval
        return {"name": self.name, "mean_diff": round(i.mean, 5), "ci": [round(i.lo, 5), round(i.hi, 5)],
                "n": i.n, "excludes_zero": i.excludes_zero}


def held_out_report(
    results: dict[str, SearchResult], baseline: SolverPolicy, test: Sequence[CodeTask], complete: Callable[[str], str]
) -> dict[str, Any]:
    base = evaluate_policy(baseline, test, complete, lam=0.0)
    evals = {m: evaluate_policy(r.best.policy, test, complete, lam=0.0) for m, r in results.items()}
    comps = []
    for m, ev in evals.items():
        diffs = [a - b for a, b in zip(ev.per_task, base.per_task, strict=True)]
        comps.append(Comparison(f"{m} - baseline", paired_bootstrap_ci(diffs)))
    if "evolution" in evals and "random" in evals:
        e, r = evals["evolution"], evals["random"]
        diffs = [a - b for a, b in zip(e.per_task, r.per_task, strict=True)]
        comps.append(Comparison("evolution - random", paired_bootstrap_ci(diffs)))
    return {
        "baseline": {"policy": baseline.key(), "held_out_score": round(base.score, 5)},
        "methods": {
            m: {
                "policy": ev.policy.key(),
                "held_out_score": round(ev.score, 5),
                "calls": ev.calls,
                "train_fitness": round(results[m].best.fitness, 5),
                "train_evaluations": results[m].evaluations,
                "train_calls": results[m].calls_spent,
            }
            for m, ev in evals.items()
        },
        "comparisons": [c.as_dict() for c in comps],
        "held_out_tasks": [t.spec.task_id for t in test],
        "call_errors": {m: ev.call_errors for m, ev in evals.items()},
        "baseline_call_errors": base.call_errors,
    }


__all__ = ["Comparison", "PolicyEval", "SearchResult", "evaluate_policy", "evolve_policy", "held_out_report",
           "mutate", "random_policy", "random_search", "split_tasks"]
