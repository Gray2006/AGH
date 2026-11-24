from __future__ import annotations

import random
from pathlib import Path

import pytest

from agh.arena import ArenaConfig
from agh.eventlog import EventLog
from agh.evolution import (
    Benchmark,
    EvolutionConfig,
    Strategy,
    StrategyMutator,
    default_benchmarks,
    evaluate_strategy,
    evolve,
    novelty_of,
)
from agh.pipeline import PARENT_SIG, m0_skeleton


@pytest.fixture()
def cfg(frozen_src: Path) -> ArenaConfig:
    return ArenaConfig.from_frozen(frozen_src)


def seed_strategy() -> Strategy:
    return Strategy(
        name="seed",
        features=tuple(PARENT_SIG.features),
        parts=("M0", "P1", "C1", "C2", "C3"),
        covered=("P1", "C1", "C2"),
        confidence=0.8,
        depth=0.9,
    )


def benchmarks() -> list[Benchmark]:
    return default_benchmarks(m0_skeleton(), PARENT_SIG.features)


def test_evaluate_seed_passes(cfg: ArenaConfig) -> None:
    result = evaluate_strategy(seed_strategy(), benchmarks(), cfg)
    assert result.passed
    assert result.fitness > 0
    assert len(result.scores) == 3


def test_evaluate_rejects_missing_parts(cfg: ArenaConfig) -> None:
    bad = Strategy(name="bad", features=("a",), parts=("M0",), covered=(), confidence=0.5, depth=0.5)
    result = evaluate_strategy(bad, benchmarks(), cfg)
    assert not result.passed
    assert result.fitness == 0.0


def test_mutator_stays_in_bounds() -> None:
    rng = random.Random(1)
    mutator = StrategyMutator(["f1", "f2"], ["M0", "P1", "C1"])
    strategy = seed_strategy()
    for _ in range(50):
        strategy = mutator.mutate(strategy, rng, "v")
    assert 0.1 <= strategy.confidence <= 0.95
    assert 0.2 <= strategy.depth <= 0.95
    assert strategy.features


def test_novelty_bounds() -> None:
    assert novelty_of(seed_strategy(), []) == 1.0


def test_evolve_runs_and_reports(cfg: ArenaConfig) -> None:
    report = evolve(
        seed_strategy(), benchmarks(), cfg, EvolutionConfig(generations=2, population=2, budget_calls=100)
    )
    data = report.as_dict()
    assert data["governance_state"] == "VERIFIED"
    assert data["archive_size"] == 1 + 2 * 2
    assert len(data["curve"]) == 3
    assert data["best"] is not None
    assert json_roundtrip(data)


def json_roundtrip(data: dict) -> bool:
    import json

    json.dumps(data)
    return True


def test_evolve_is_seeded(cfg: ArenaConfig) -> None:
    first = evolve(seed_strategy(), benchmarks(), cfg, EvolutionConfig(generations=2, population=2, seed=3))
    second = evolve(seed_strategy(), benchmarks(), cfg, EvolutionConfig(generations=2, population=2, seed=3))
    assert first.as_dict()["best"]["fitness"] == second.as_dict()["best"]["fitness"]


def test_evolve_stops_on_budget(cfg: ArenaConfig) -> None:
    report = evolve(
        seed_strategy(), benchmarks(), cfg, EvolutionConfig(generations=5, population=3, budget_calls=1)
    )
    assert any("预算" in note for note in report.notes)


def test_lineage_parents_exist(cfg: ArenaConfig) -> None:
    report = evolve(seed_strategy(), benchmarks(), cfg, EvolutionConfig(generations=2, population=2))
    ids = {row["id"] for row in report.lineage}
    for row in report.lineage:
        if row["parent"] is not None:
            assert row["parent"] in ids


def test_evolution_log_is_verifiable(cfg: ArenaConfig, tmp_path: Path) -> None:
    log_path = tmp_path / "events.jsonl"
    report = evolve(
        seed_strategy(),
        benchmarks(),
        cfg,
        EvolutionConfig(generations=1, population=2),
        log=EventLog(log_path),
    )
    assert report.log_ok
    assert report.log_entries > 0
    EventLog(log_path).verify()  # 不抛即通过


def test_hill_climb_is_deterministic(cfg: ArenaConfig) -> None:
    from agh.evolution_llm import hill_climb

    first = hill_climb(seed_strategy(), benchmarks(), cfg, seed=4, evaluations=4)
    second = hill_climb(seed_strategy(), benchmarks(), cfg, seed=4, evaluations=4)
    assert first == second


def test_reference_rewards_completing_missing_edge(cfg: ArenaConfig) -> None:
    """参照签名取自骨架：补全缺失的 P1-C3 应当加分，而不是被结构距离惩罚。"""
    from agh.evolution import Strategy, evaluate_strategy

    full = Strategy(
        name="full",
        features=("M0-P1", "P1-C1", "P1-C2", "P1-C3"),
        parts=("M0", "P1", "C1", "C2", "C3"),
        covered=("P1", "C1", "C2"),
        confidence=0.8,
        depth=0.9,
    )
    partial = Strategy(
        name="partial",
        features=("M0-P1", "P1-C1", "P1-C2"),
        parts=("M0", "P1", "C1", "C2", "C3"),
        covered=("P1", "C1", "C2"),
        confidence=0.8,
        depth=0.9,
    )
    benches = benchmarks()
    assert evaluate_strategy(full, benches, cfg).fitness > evaluate_strategy(partial, benches, cfg).fitness


def test_archive_select_elite_only_skips_rejected() -> None:
    from agh.evolution import Archive, Variant

    archive = Archive()
    strategy = Strategy("r", ("a-b",), ("a",), ("a",), 0.5, 0.5)
    archive.add(Variant("rejected", None, 1, strategy, 0.9, [], accepted=False))
    archive.add(Variant("accepted", None, 1, strategy, 0.1, [], accepted=True))
    picked = archive.select(random.Random(0), 3, elite_only=True)
    assert picked.variant_id == "accepted"
