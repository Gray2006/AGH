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
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        # 非 UTF-8（别的工具按 GBK 写的）、坏 JSON、读不动：跳过这一份，不连累整张表
        return None
    if not isinstance(data, dict):
        # 合法 JSON 但不是对象，字段取不到，同样跳过
        return None
    return data


def _row(name: str, data: dict[str, Any]) -> Row:
    row = Row(name=name)
    if name == "m0":
        scores = data.get("scores")
        scores = scores if isinstance(scores, dict) else {}
        row.values = {"winner": data.get("winner"), "score": scores.get(data.get("winner"))}
    elif name == "experiment":
        row.values = {"contested": data.get("contested_rate"), "metrics": data.get("metrics")}
    elif name == "ablation":
        rows = data.get("rows")
        row.values = {"rows": len(rows) if isinstance(rows, list) else 0}
    elif name.startswith("llm_"):
        delta = data.get("delta")
        row.values = {
            "n": data.get("benchmarks") or data.get("valid"),
            "llm": data.get("llm_mean"),
            "rule": data.get("rule_mean"),
            "delta": delta.get("mean") if isinstance(delta, dict) else None,
        }
    elif name.startswith("human"):
        row.values = {
            "n": data.get("n"),
            "agreement": data.get("agreement"),
            "kappa": data.get("cohen_kappa"),
            "ece": data.get("ece"),
        }
    return row


def collect(runs_dir: str | Path) -> dict[str, Any]:
    root = Path(runs_dir)
    rows: list[Row] = []
    for name, rel in CANDIDATES.items():
        data = _load(root / rel)
        if data is None:
            continue
        rows.append(_row(name, data))
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
