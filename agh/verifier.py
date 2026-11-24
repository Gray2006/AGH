"""独立验证器：把「候选自报」的指标换成「可核对的结构证据」。

垂直一致性此前是自报的，候选写一串 `vertical_moves` 就能拿分。这里给一个
不读自报深度、只核对结构证据的打分器：

对骨架里的每个垂直移动节点，要求同时满足
1. 该节点出现在 candidate.parts 里；
2. candidate.content.edges（或签名里的 `a-b` 特征）里存在一条指向它的边。

两个条件都可核对，且与评分里的结构距离互相牵制：硬塞节点会拉大结构距离。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .contracts import GestaltReconstruction, Skeleton


class Verifier(Protocol):
    name: str

    def score(self, candidate: GestaltReconstruction, skeleton: Skeleton) -> float: ...


@dataclass(frozen=True)
class StructuralVerifier:
    """按 parts + edges 证据核对垂直移动，不看自报深度。"""

    name: str = "structural"

    def score(self, candidate: GestaltReconstruction, skeleton: Skeleton) -> float:
        vertical_nodes = [m.node for m in skeleton.moves if m.vertical]
        if not vertical_nodes:
            return 0.0
        parts = set(candidate.parts)
        edges: set[tuple[str, str]] = set()
        for edge in candidate.content.get("edges", []) or []:
            if isinstance(edge, (list, tuple)) and len(edge) == 2:
                edges.add((str(edge[0]), str(edge[1])))
        for feature in candidate.signature.features:
            if "-" in feature:
                a, b = feature.split("-", 1)
                edges.add((a, b))
        supported = 0
        for node in vertical_nodes:
            if node not in parts:
                continue
            has_parent = any(b == node for _, b in edges)
            if has_parent:
                supported += 1
        return supported / len(vertical_nodes)


@dataclass(frozen=True)
class CoverageVerifier:
    """只核对覆盖率：必需项是否都在 parts 里。"""

    name: str = "coverage"

    def score(self, candidate: GestaltReconstruction, skeleton: Skeleton) -> float:
        required = set(skeleton.required_items)
        if not required:
            return 0.0
        return len(required & set(candidate.parts)) / len(required)


def make_verifier(kind: str) -> Verifier:
    if kind == "structural":
        return StructuralVerifier()
    if kind == "coverage":
        return CoverageVerifier()
    raise ValueError(f"未知验证器: {kind}")


__all__ = ["CoverageVerifier", "StructuralVerifier", "Verifier", "make_verifier"]
