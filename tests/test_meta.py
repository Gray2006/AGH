from __future__ import annotations

import random
from pathlib import Path

import pytest

from agh.arena import ArenaConfig
from agh.evolution import EvolutionConfig
from agh.evolution_sharded import ParamGenome
from agh.meta import (
    OPERATORS,
    OperatorBandit,
    apply_operator,
    curriculum_benchmarks,
    meta_evolve,
)


@pytest.fixture()
def cfg(frozen_src: Path) -> ArenaConfig:
    return ArenaConfig.from_frozen(frozen_src)


def test_bandit_tries_each_operator_first() -> None:
    bandit = OperatorBandit()
    rng = random.Random(0)
    picked = []
    for _ in range(len(OPERATORS)):
        op = bandit.choose(rng)
        picked.append(op)
        bandit.update(op, 0.0)
    assert set(picked) == set(OPERATORS)


def test_bandit_prefers_rewarded_operator() -> None:
    bandit = OperatorBandit(c=0.0)
    for op in OPERATORS:
        bandit.update(op, 0.0)
    bandit.update("tau_up", 1.0)
    bandit.counts["tau_up"] += 5
    rng = random.Random(0)
    assert bandit.choose(rng) == "tau_up"


def test_apply_operator_keeps_weights_normalized(cfg: ArenaConfig) -> None:
    genome = ParamGenome.from_config(cfg)
    rng = random.Random(1)
    for op in OPERATORS:
        out = apply_operator(genome, op, rng, 0.1)
        assert abs(sum(out.weights.values()) - 1.0) < 1e-6
        assert 0.05 <= out.dissent_tau <= 0.9


def test_curriculum_gets_harder() -> None:
    easy = curriculum_benchmarks(1, 0)
    hard = curriculum_benchmarks(4, 0)
    assert len({n for b in hard for n in b.skeleton.nodes}) >= len(
        {n for b in easy for n in b.skeleton.nodes}
    )
    assert len(hard[0].skeleton.edges) >= len(easy[0].skeleton.edges)


def test_meta_evolve_reports(cfg: ArenaConfig) -> None:
    report = meta_evolve(
        cfg,
        EvolutionConfig(generations=1, population=2, resamples=100),
        rounds=3,
        seed=1,
        patience=1,
    )
    data = report.as_dict()
    assert data["rounds"] == 3
    assert len(data["curve"]) == 4
    assert set(data["bandit"]) == set(OPERATORS)
    assert data["levels"][-1] >= data["levels"][0]
    import json

    json.dumps(data)


def test_weight_down_never_goes_negative(cfg: ArenaConfig) -> None:
    genome = ParamGenome.from_config(cfg)
    rng = random.Random(3)
    for _ in range(30):
        genome = apply_operator(genome, "weight_down", rng, 0.2)
        assert all(v >= 0.0 for v in genome.weights.values())
