"""真实失败样本任务族。

用途：人工降质是合成的，真实模型在新基准上给出的失败重构不是。
把一个「模型给出、但分数低于种子」的重构固化成种子，进化必须从错误起点爬回来——
这条曲线比「从完美种子往下掉」更接近真实场景。

样本来自真实模型运行，但以 JSON fixture 形式提交；测试与 CI 不调用模型。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .benchmarks import _reference
from .contracts import Skeleton, SkeletonMove
from .evolution import Benchmark, Strategy

FAILURE_VERSION = 1


@dataclass(frozen=True)
class FailureCase:
    case_id: str
    skeleton: Skeleton
    seed: Strategy
    failed_score: float
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": FAILURE_VERSION,
            "case_id": self.case_id,
            "skeleton": _skeleton_to_dict(self.skeleton),
            "seed": _strategy_to_dict(self.seed),
            "failed_score": self.failed_score,
            "note": self.note,
        }

    def to_benchmark(self) -> Benchmark:
        return Benchmark(skeleton=self.skeleton, parent=_reference(self.skeleton))


def _skeleton_to_dict(s: Skeleton) -> dict[str, Any]:
    return {
        "skeleton_id": s.skeleton_id,
        "nodes": list(s.nodes),
        "edges": [[a, b] for a, b in s.edges],
        "required_items": list(s.required_items),
        "moves": [
            {
                "node": m.node,
                "vertical": m.vertical,
                "declared_depth": m.declared_depth,
                "preserved_depth": m.preserved_depth,
            }
            for m in s.moves
        ],
        "min_vertical_moves": s.min_vertical_moves,
    }


def _skeleton_from_dict(d: dict[str, Any]) -> Skeleton:
    return Skeleton(
        skeleton_id=d["skeleton_id"],
        nodes=list(d["nodes"]),
        edges=[(a, b) for a, b in d["edges"]],
        required_items=list(d["required_items"]),
        moves=[
            SkeletonMove(
                node=m["node"],
                vertical=m.get("vertical", True),
                declared_depth=float(m.get("declared_depth", 0.0)),
                preserved_depth=float(m.get("preserved_depth", 0.0)),
            )
            for m in d.get("moves", [])
        ],
        min_vertical_moves=int(d.get("min_vertical_moves", 0)),
    )


def _strategy_to_dict(s: Strategy) -> dict[str, Any]:
    return {
        "name": s.name,
        "features": list(s.features),
        "parts": list(s.parts),
        "covered": list(s.covered),
        "confidence": s.confidence,
        "depth": s.depth,
    }


def _strategy_from_dict(d: dict[str, Any]) -> Strategy:
    return Strategy(
        name=d["name"],
        features=tuple(d["features"]),
        parts=tuple(d["parts"]),
        covered=tuple(d["covered"]),
        confidence=float(d["confidence"]),
        depth=float(d["depth"]),
    )


def load_failures(path: str | Path) -> list[FailureCase]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    items = raw["cases"] if isinstance(raw, dict) else raw
    return [
        FailureCase(
            case_id=item["case_id"],
            skeleton=_skeleton_from_dict(item["skeleton"]),
            seed=_strategy_from_dict(item["seed"]),
            failed_score=float(item["failed_score"]),
            note=item.get("note", ""),
        )
        for item in items
    ]


def dump_failures(cases: list[FailureCase], path: str | Path) -> None:
    payload = {"version": FAILURE_VERSION, "cases": [c.as_dict() for c in cases]}
    Path(path).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def failures_to_benchmarks(cases: list[FailureCase]) -> list[Benchmark]:
    return [c.to_benchmark() for c in cases]


__all__ = [
    "FAILURE_VERSION",
    "FailureCase",
    "dump_failures",
    "failures_to_benchmarks",
    "load_failures",
]
