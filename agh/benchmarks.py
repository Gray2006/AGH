"""可配置的基准生成器。

固定 3 个骨架太窄：任何局部搜索都能到同一个平台，对照没有区分度。
这里按节点数、边密度、必需项比例生成一批结构不同的骨架，
用来做跨骨架的适应度评估（避免只对单一骨架过拟合）。
"""

from __future__ import annotations

import random
from collections.abc import Sequence

from .contracts import AbstractSignature, Skeleton, SkeletonMove
from .evolution import Benchmark


def _reference(skeleton: Skeleton) -> AbstractSignature:
    return AbstractSignature(
        signature_id=f"ref-{skeleton.skeleton_id}",
        features=[f"{a}-{b}" for a, b in skeleton.edges],
    )


def make_skeleton(
    index: int,
    rng: random.Random,
    *,
    min_nodes: int = 5,
    max_nodes: int = 5,
    extra_edges: int = 2,
    required_ratio: float = 0.5,
) -> Skeleton:
    n = rng.randint(min_nodes, max_nodes)
    nodes = [f"N{i}" for i in range(n)]
    edges: list[tuple[str, str]] = []
    # 先连成一棵树，保证从 N0 可达
    for i in range(1, n):
        parent = nodes[rng.randrange(i)]
        edges.append((parent, nodes[i]))
    # 再加若干条不重复的额外边，保持无环（只从低序号指向高序号）
    for _ in range(extra_edges):
        a = rng.randrange(n - 1)
        b = rng.randrange(a + 1, n)
        edge = (nodes[a], nodes[b])
        if edge not in edges:
            edges.append(edge)
    required_count = max(1, min(n, round(n * required_ratio)))
    required = sorted(rng.sample(nodes, k=required_count))
    if nodes[-1] not in required:
        required[-1] = nodes[-1]
    moves = []
    for _, node in edges[: max(1, len(edges) // 2)]:
        vertical = rng.random() < 0.6
        moves.append(
            SkeletonMove(
                node=node,
                vertical=vertical,
                declared_depth=round(rng.uniform(0.3, 0.9), 2),
                preserved_depth=round(rng.uniform(0.3, 0.9), 2),
            )
            if vertical
            else SkeletonMove(node=node, vertical=False)
        )
    return Skeleton(
        skeleton_id=f"sk-gen-{index}",
        nodes=nodes,
        edges=edges,
        required_items=required,
        moves=moves,
        min_vertical_moves=1 if any(m.vertical for m in moves) else 0,
    )


FAMILIES: dict[str, dict[str, float | int]] = {
    "default": {},
    "hard": {"min_nodes": 7, "max_nodes": 9, "extra_edges": 4, "required_ratio": 0.6},
    "wide": {"min_nodes": 8, "max_nodes": 10, "extra_edges": 6, "required_ratio": 0.5},
    "deep": {"min_nodes": 10, "max_nodes": 12, "extra_edges": 3, "required_ratio": 0.7},
}


def generate_benchmarks(
    count: int = 10,
    *,
    seed: int = 0,
    min_nodes: int = 5,
    max_nodes: int = 5,
    extra_edges: int = 2,
    required_ratio: float = 0.5,
    family: str = "default",
) -> list[Benchmark]:
    if family != "default":
        preset = FAMILIES.get(family)
        if preset is None:
            raise ValueError(f"未知骨架族: {family}（可选: {', '.join(FAMILIES)}）")
        min_nodes = int(preset.get("min_nodes", min_nodes))
        max_nodes = int(preset.get("max_nodes", max_nodes))
        extra_edges = int(preset.get("extra_edges", extra_edges))
        required_ratio = float(preset.get("required_ratio", required_ratio))
    if count <= 0:
        raise ValueError("count 必须为正")
    rng = random.Random(seed)
    benchmarks: list[Benchmark] = []
    for index in range(count):
        skeleton = make_skeleton(
            index,
            rng,
            min_nodes=min_nodes,
            max_nodes=max_nodes,
            extra_edges=extra_edges,
            required_ratio=required_ratio,
        )
        benchmarks.append(Benchmark(skeleton=skeleton, parent=_reference(skeleton)))
    return benchmarks


def feature_pool(benchmarks: Sequence[Benchmark]) -> list[str]:
    """所有基准里出现过的边特征与节点。"""
    features: set[str] = set()
    for bench in benchmarks:
        features.update(f"{a}-{b}" for a, b in bench.skeleton.edges)
        features.update(bench.skeleton.nodes)
    return sorted(features)


__all__ = ["feature_pool", "generate_benchmarks", "make_skeleton"]
