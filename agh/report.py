"""汇总报告：把 runs/ 下各实验的结果收成一张表。

    python -m agh report --runs runs

只读，不重跑；缺哪个文件就跳过哪个。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Row:
    name: str
    values: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, **self.values}


CANDIDATES = {
    "m0": "m0/report.json",
    "experiment": "g1/experiment.json",
    "ablation": "g1/ablation.json",
    "llm_bench_10": "g1/llm-bench.json",
    "llm_hard_12": "g1/llm-hard.json",
    "llm_hard_50": "g1/llm-hard50.json",
    "human_calibration": "g1/human-calibration.json",
    "human_calibration_real": "g1/human-calibration-real.json",
}


def _load(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def collect(runs_dir: str | Path) -> dict[str, Any]:
    root = Path(runs_dir)
    rows: list[Row] = []
    for name, rel in CANDIDATES.items():
        data = _load(root / rel)
        if data is None:
            continue
        row = Row(name=name)
        if name == "m0":
            row.values = {"winner": data.get("winner"), "score": data.get("scores", {}).get(data.get("winner"))}
        elif name == "experiment":
            row.values = {"contested": data.get("contested_rate"), "metrics": data.get("metrics")}
        elif name == "ablation":
            row.values = {"rows": len(data.get("rows", []))}
        elif name.startswith("llm_"):
            row.values = {
                "n": data.get("benchmarks") or data.get("valid"),
                "llm": data.get("llm_mean"),
                "rule": data.get("rule_mean"),
                "delta": (data.get("delta") or {}).get("mean"),
            }
        elif name.startswith("human"):
            row.values = {
                "n": data.get("n"),
                "agreement": data.get("agreement"),
                "kappa": data.get("cohen_kappa"),
                "ece": data.get("ece"),
            }
        rows.append(row)
    return {"runs_dir": str(root), "available": [r.name for r in rows], "rows": [r.as_dict() for r in rows]}


def render(payload: dict[str, Any]) -> str:
    lines = [f"AGH 报告（{payload['runs_dir']}）", ""]
    if not payload["rows"]:
        return "\n".join([*lines, "没有找到任何运行结果"])
    for row in payload["rows"]:
        cells = ", ".join(f"{k}={v}" for k, v in row.items() if k != "name")
        lines.append(f"- {row['name']}: {cells}")
    return "\n".join(lines)


__all__ = ["Row", "collect", "render"]
