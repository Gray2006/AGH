"""降质种子与跨轮精英延续：让 daemon 在更难的任务族上有真实梯度。"""

from __future__ import annotations

import random
from pathlib import Path

import pytest

from agh.arena import ArenaConfig
from agh.benchmarks import generate_benchmarks
from agh.evolution import EvolutionConfig
from agh.evolution_sharded import combined_evolve, seed_for, sharded_evolve
from agh.verifier import StructuralVerifier


@pytest.fixture()
def cfg(frozen_src: Path) -> ArenaConfig:
    return ArenaConfig.from_frozen(frozen_src)


def test_seed_degrade_drops_but_keeps_some() -> None:
    bench = generate_benchmarks(1, seed=0)[0]
    rng = random.Random("0:sk-gen-0")
    full = seed_for(bench)
    reduced = seed_for(bench, degrade=0.4, rng=rng)
    assert len(reduced.features) < len(full.features)
    assert len(reduced.covered) < len(full.covered)
    assert reduced.features and reduced.covered
    # 确定性：同 rng 种子必须还原同一降质结果
    again = seed_for(bench, degrade=0.4, rng=random.Random("0:sk-gen-0"))
    assert again.features == reduced.features
    assert again.covered == reduced.covered


def test_degrade_zero_keeps_full_seed() -> None:
    bench = generate_benchmarks(1, seed=0)[0]
    assert seed_for(bench, degrade=0.0) == seed_for(bench)


def test_sharded_evolve_uses_carried_strategy(cfg: ArenaConfig) -> None:
    benches = generate_benchmarks(2, seed=0)
    first = sharded_evolve(
        benches, cfg, EvolutionConfig(generations=1, population=1, seed=0), verifier=StructuralVerifier()
    )
    carry = {s.skeleton_id: s.strategy for s in first.shards}
    second = sharded_evolve(
        benches,
        cfg,
        EvolutionConfig(generations=1, population=1, seed=0),
        verifier=StructuralVerifier(),
        carry=carry,
    )
    baseline = {s.skeleton_id: s.fitness for s in first.shards}
    for shard in second.shards:
        assert shard.fitness >= baseline[shard.skeleton_id] - 1e-9


def test_combined_evolve_reports_carry(cfg: ArenaConfig) -> None:
    benches = generate_benchmarks(2, seed=0)
    report = combined_evolve(
        benches,
        cfg,
        EvolutionConfig(generations=1, population=1, seed=0),
        rounds=1,
        params_per_round=1,
        verifier=StructuralVerifier(),
        reference_cfg=cfg,
        seed_degrade=0.4,
    )
    assert set(report.carry) == {b.skeleton.skeleton_id for b in benches}
