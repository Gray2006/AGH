from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from agh.arena import ArenaConfig
from agh.evolution import EvolutionConfig, Strategy, default_benchmarks
from agh.evolution_llm import (
    LlmStrategyMutator,
    compare_search,
    hill_climb,
    random_search,
    random_strategy,
)
from agh.pipeline import PARENT_SIG, m0_skeleton


@pytest.fixture()
def cfg(frozen_src: Path) -> ArenaConfig:
    return ArenaConfig.from_frozen(frozen_src)


def seed() -> Strategy:
    return Strategy(
        name="seed",
        features=tuple(PARENT_SIG.features),
        parts=("M0", "P1", "C1", "C2", "C3"),
        covered=("P1", "C1", "C2"),
        confidence=0.8,
        depth=0.9,
    )


def test_llm_mutator_uses_valid_json() -> None:
    pool = [*list(PARENT_SIG.features), "extra"]
    reply = json.dumps(
        {"features": ["M0-P1", "P1-C1", "extra"], "parts": ["M0", "P1"],
         "covered": ["P1"], "confidence": 0.7, "depth": 0.6}
    )
    mutator = LlmStrategyMutator(pool, ["M0", "P1", "C1"], lambda _p: reply)
    child = mutator.mutate(seed(), random.Random(1), "v1")
    assert "extra" in child.features
    assert 0.1 <= child.confidence <= 0.95
    assert child.name == "v1"


def test_llm_mutator_filters_out_of_pool_and_falls_back() -> None:
    mutator = LlmStrategyMutator(["M0-P1"], ["M0"], lambda _p: '{"features": ["evil:inject"]}')
    child = mutator.mutate(seed(), random.Random(1), "v1")
    assert "evil:inject" not in child.features
    assert child.features


def test_llm_mutator_falls_back_on_garbage() -> None:
    mutator = LlmStrategyMutator(list(PARENT_SIG.features), ["M0", "P1"], lambda _p: "不是 JSON")
    child = mutator.mutate(seed(), random.Random(2), "v1")
    assert child.features


def test_random_strategy_bounds() -> None:
    rng = random.Random(3)
    strategy = random_strategy(["a", "b", "c"], ["M0", "P1"], rng, "r")
    assert 0.1 <= strategy.confidence <= 0.95
    assert 0.2 <= strategy.depth <= 0.95
    assert strategy.features


def test_random_search_deterministic(cfg: ArenaConfig) -> None:
    benches = default_benchmarks(m0_skeleton(), PARENT_SIG.features)
    first = random_search(benches, cfg, seed=5, evaluations=5)
    second = random_search(benches, cfg, seed=5, evaluations=5)
    assert first == second


def test_compare_search_reports(cfg: ArenaConfig) -> None:
    benches = default_benchmarks(m0_skeleton(), PARENT_SIG.features)
    comparison = compare_search(
        seed(), benches, cfg, EvolutionConfig(generations=1, population=2), runs=2, resamples=100
    )
    data = comparison.as_dict()
    assert data["runs"] == 2
    assert set(data["baselines"]) == {"random", "hill"}
    assert len(data["rows"]) == 2
    for row in data["rows"]:
        assert row["delta"]["lo"] <= row["delta"]["mean"] <= row["delta"]["hi"]
        assert 0.0 <= row["p_value"] <= 1.0
        assert row["holm_threshold"] > 0


def test_hill_climb_restarts_deterministic(cfg: ArenaConfig) -> None:
    benches = default_benchmarks(m0_skeleton(), PARENT_SIG.features)
    first = hill_climb(seed(), benches, cfg, seed=2, evaluations=3, restarts=3)
    second = hill_climb(seed(), benches, cfg, seed=2, evaluations=3, restarts=3)
    assert first == second


def test_compare_search_multi_seed(cfg: ArenaConfig) -> None:
    benches = default_benchmarks(m0_skeleton(), PARENT_SIG.features)
    comparison = compare_search(
        seed(),
        benches,
        cfg,
        EvolutionConfig(generations=1, population=2),
        runs=2,
        seeds_per_run=2,
        resamples=100,
    )
    data = comparison.as_dict()
    assert data["runs"] == 2
    assert len(data["evolution_scores"]) == 2
    assert len(data["rows"]) == 2


class CountingMutator:
    def __init__(self) -> None:
        self.calls = 0

    def mutate(self, parent, rng, name):
        from agh.evolution import Strategy

        self.calls += 1
        return Strategy(
            name=name,
            features=parent.features,
            parts=parent.parts,
            covered=parent.covered,
            confidence=parent.confidence,
            depth=parent.depth,
        )


def test_compare_search_uses_injected_mutator(cfg: ArenaConfig) -> None:
    benches = default_benchmarks(m0_skeleton(), PARENT_SIG.features)
    mutator = CountingMutator()
    compare_search(
        seed(),
        benches,
        cfg,
        EvolutionConfig(generations=1, population=2),
        runs=1,
        seeds_per_run=1,
        resamples=100,
        mutator=mutator,
    )
    assert mutator.calls == 2
