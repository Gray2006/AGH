from __future__ import annotations

from pathlib import Path

import pytest

from agh.arena import ArenaConfig
from agh.benchmarks import generate_benchmarks
from agh.evolution import EvolutionConfig
from agh.evolution_sharded import (
    ParamGenome,
    anneal_scale,
    combined_evolve,
    mutate_params,
    normalize_weights,
    seed_for,
    sharded_evolve,
)


@pytest.fixture()
def cfg(frozen_src: Path) -> ArenaConfig:
    return ArenaConfig.from_frozen(frozen_src)


def test_seed_for_is_valid() -> None:
    bench = generate_benchmarks(1, seed=0)[0]
    strategy = seed_for(bench)
    assert set(strategy.parts) == set(bench.skeleton.nodes)
    assert strategy.features


def test_sharded_evolve_reports_each_benchmark(cfg: ArenaConfig) -> None:
    benches = generate_benchmarks(3, seed=1)
    report = sharded_evolve(benches, cfg, EvolutionConfig(generations=1, population=2))
    assert len(report.shards) == 3
    assert report.mean_fitness > 0
    assert report.evaluations == 3 * 3


def test_mutate_params_bounded() -> None:
    import random

    cfg = ArenaConfig.from_frozen(Path("config/frozen"))
    genome = ParamGenome.from_config(cfg)
    rng = random.Random(1)
    for _ in range(30):
        genome = mutate_params(genome, rng)
    for value in genome.weights.values():
        assert 0.0 <= value <= 1.0
    assert 0.05 <= genome.dissent_tau <= 0.9


def test_combined_evolve_reports(cfg: ArenaConfig) -> None:
    benches = generate_benchmarks(3, seed=2)
    report = combined_evolve(
        benches, cfg, EvolutionConfig(generations=1, population=2), rounds=1, params_per_round=2
    )
    data = report.as_dict()
    assert data["rounds"] == 1
    assert len(data["curve"]) == 2
    assert data["single_mean"] > 0
    assert data["per_benchmark_delta"] is not None
    assert data["per_benchmark_delta"]["n"] == 3
    assert set(data["best_params"]["weights"])
    import json

    json.dumps(data)


def test_param_genome_config_roundtrip(cfg: ArenaConfig) -> None:
    genome = ParamGenome.from_config(cfg)
    new_cfg = genome.config(cfg)
    assert new_cfg.weights == cfg.weights
    assert new_cfg.dissent_tau == cfg.dissent_tau


def test_anneal_schedule() -> None:
    assert anneal_scale(0, 4) == 0.1
    assert anneal_scale(1, 4) == 0.1
    assert anneal_scale(2, 4) == 0.02
    assert anneal_scale(3, 4) == 0.02


def test_mutation_step_respects_scale(cfg: ArenaConfig) -> None:
    import random

    genome = ParamGenome.from_config(cfg)
    rng = random.Random(2)
    for _ in range(20):
        candidate = mutate_params(genome, rng, scale=0.02)
        for key, value in candidate.weights.items():
            assert abs(value - genome.weights[key]) <= 0.02 + 1e-9
        genome = candidate


def test_mutated_weights_stay_normalized() -> None:
    import random

    cfg = ArenaConfig.from_frozen(Path("config/frozen"))
    genome = ParamGenome.from_config(cfg)
    rng = random.Random(5)
    for _ in range(40):
        genome = mutate_params(genome, rng, scale=0.1)
        assert abs(sum(genome.weights.values()) - 1.0) < 1e-6


def test_normalize_weights() -> None:
    out = normalize_weights({"a": 0.2, "b": 0.2, "c": 0.7})
    assert abs(sum(out.values()) - 1.0) < 1e-6
    assert out["c"] > out["a"]
