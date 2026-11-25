"""离线基准的回归测试。

模拟模型是确定性的（固定种子），所以分数可以精确断言。
任何改动导致数字变化都会在这里暴露——包括「不小心改了评分逻辑」和「加了新题」。

改题库或评分口径时，这里的期望值需要同步更新，并在 CHANGELOG 里注明。
"""

from __future__ import annotations

import pytest

from agh.code_evolution import evolve_policy, held_out_report, random_search, split_tasks
from agh.codesolve import SolverPolicy
from agh.codetasks import TASKS
from agh.simulated import SimulatedCoder

BUDGET = 200
SEED = 0

# 2026-11-25 的基线（20 题、held-out 4、p_correct=0.4）
EXPECTED = {
    "baseline": 0.2875,
    "evolution": 0.1875,
    "random": 0.4375,
}


@pytest.fixture(scope="module")
def report() -> dict:
    train, test = split_tasks(list(TASKS.values()), 4, seed=SEED)
    coder = SimulatedCoder(p_correct=0.4, seed=SEED)
    return held_out_report(
        {
            "evolution": evolve_policy(train, coder, BUDGET, seed=SEED),
            "random": random_search(train, coder, BUDGET, seed=SEED),
        },
        SolverPolicy(),
        test,
        coder,
    )


def test_baseline_is_stable(report: dict) -> None:
    assert report["baseline"]["held_out_score"] == pytest.approx(
        EXPECTED["baseline"], abs=1e-9
    )


def test_evolution_is_stable(report: dict) -> None:
    assert report["methods"]["evolution"]["held_out_score"] == pytest.approx(
        EXPECTED["evolution"], abs=1e-9
    )


def test_random_is_stable(report: dict) -> None:
    assert report["methods"]["random"]["held_out_score"] == pytest.approx(
        EXPECTED["random"], abs=1e-9
    )


def test_same_seed_same_result() -> None:
    """同样的种子必须给出同样的分数——这是「可复现」的底线。"""
    train, _test = split_tasks(list(TASKS.values()), 4, seed=SEED)
    coder = SimulatedCoder(p_correct=0.4, seed=SEED)
    first = evolve_policy(train, coder, 80, seed=SEED).best.fitness
    second = evolve_policy(train, coder, 80, seed=SEED).best.fitness
    assert first == second
