from __future__ import annotations

from pathlib import Path

import pytest

from agh.arena import ArenaConfig
from agh.benchmarks import feature_pool, generate_benchmarks
from agh.evolution import EvolutionConfig, Strategy, evolve


@pytest.fixture()
def cfg(frozen_src: Path) -> ArenaConfig:
    return ArenaConfig.from_frozen(frozen_src)


def test_generate_is_deterministic() -> None:
    a = generate_benchmarks(5, seed=7)
    b = generate_benchmarks(5, seed=7)
    assert [x.skeleton.model_dump() for x in a] == [x.skeleton.model_dump() for x in b]


def test_generated_skeletons_are_valid() -> None:
    for bench in generate_benchmarks(8, seed=3):
        sk = bench.skeleton
        assert sk.nodes
        assert set(sk.required_items) <= set(sk.nodes)
        for a, b in sk.edges:
            assert a in sk.nodes and b in sk.nodes
            assert a != b
        assert sk.skeleton_id.startswith("sk-gen-")


def test_feature_pool_covers_edges_and_nodes() -> None:
    benches = generate_benchmarks(3, seed=1)
    pool = feature_pool(benches)
    first = benches[0].skeleton
    assert nodes_in(first.nodes, pool)
    assert f"{first.edges[0][0]}-{first.edges[0][1]}" in pool


def nodes_in(nodes: list[str], pool: list[str]) -> bool:
    return all(n in pool for n in nodes)


def test_evolve_on_generated_benchmarks(cfg: ArenaConfig) -> None:
    benches = generate_benchmarks(4, seed=2)
    seed = Strategy(
        name="seed",
        features=tuple(feature_pool(benches)[:2]),
        parts=tuple(benches[0].skeleton.nodes),
        covered=tuple(benches[0].skeleton.required_items),
        confidence=0.6,
        depth=0.7,
    )
    report = evolve(seed, benches, cfg, EvolutionConfig(generations=1, population=2, budget_calls=50))
    assert report.archive_size == 3
    assert report.best is not None
