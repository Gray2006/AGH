"""审计日志的统计视图：按模型、按小时聚合。

`audit-diff` 比较两份日志，这里只看一份的分布。
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .eventlog import EventLog


@dataclass(frozen=True)
class AuditStats:
    log: str
    total_calls: int
    total_tokens: int
    flags: int
    by_model: dict[str, dict[str, int]]
    by_hour: dict[str, int]
    first_ts: str
    last_ts: str
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "log": self.log,
            "total_calls": self.total_calls,
            "total_tokens": self.total_tokens,
            "flags": self.flags,
            "by_model": self.by_model,
            "by_hour": self.by_hour,
            "first_ts": self.first_ts,
            "last_ts": self.last_ts,
            "notes": list(self.notes),
        }


def _iso(ts_ms: int) -> str:
    try:
        return datetime.fromtimestamp(ts_ms / 1000, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (OverflowError, OSError, ValueError):
        return ""


def compute_stats(log_path: str | Path, *, granularity: str = "hour") -> AuditStats:
    """granularity: "hour" 或 "day"。"""
    if granularity not in ("hour", "day"):
        raise ValueError(f"granularity 只能是 hour 或 day，收到 {granularity!r}")
    path = Path(log_path)
    log = EventLog(path)
    log.verify()
    # EventLog 构造时已全量读入并校验；再 stream 一遍等于读两遍，这里直接用 entries
    entries = log.entries

    models: dict[str, dict[str, int]] = defaultdict(lambda: {"calls": 0, "tokens": 0})
    hours: Counter[str] = Counter()
    total_tokens = 0
    calls = 0
    flags = 0
    stamps: list[int] = []

    for entry in entries:
        if entry.ts:
            stamps.append(entry.ts)
        if entry.type == "llm.flag":
            flags += 1
            continue
        if entry.type != "llm.call":
            continue
        calls += 1
        payload = entry.payload
        model = str(payload.get("model") or "unknown")
        try:
            tokens = int(payload.get("tokens", 0) or 0)
        except (TypeError, ValueError):
            tokens = 0
        models[model]["calls"] += 1
        models[model]["tokens"] += tokens
        total_tokens += tokens
        bucket = _iso(entry.ts)[: 13 if granularity == "hour" else 10]
        if bucket:
            hours[bucket] += 1

    notes: list[str] = []
    if calls == 0:
        notes.append("没有 llm.call 记录")
    if flags:
        notes.append(f"{flags} 条标记")
    if models:
        top = max(models.items(), key=lambda kv: kv[1]["tokens"])
        notes.append(f"token 最多的是 {top[0]}（{top[1]['tokens']}）")

    return AuditStats(
        log=str(path),
        total_calls=calls,
        total_tokens=total_tokens,
        flags=flags,
        by_model={k: dict(v) for k, v in sorted(models.items())},
        by_hour=dict(sorted(hours.items())),
        first_ts=_iso(min(stamps)) if stamps else "",
        last_ts=_iso(max(stamps)) if stamps else "",
        notes=notes,
    )


def render(stats: AuditStats) -> str:
    lines = [
        f"日志：{stats.log}",
        f"时间范围：{stats.first_ts or '-'} → {stats.last_ts or '-'}",
        f"调用 {stats.total_calls} 次，tokens {stats.total_tokens}，标记 {stats.flags}",
        "",
        "按模型：",
    ]
    if stats.by_model:
        for model, data in stats.by_model.items():
            lines.append(f"  {model}: {data['calls']} 次 / {data['tokens']} tokens")
    else:
        lines.append("  （无）")
    if stats.by_hour:
        unit = "按天" if len(next(iter(stats.by_hour))) == 10 else "按小时"
        lines += ["", f"{unit}："]
        for hour, count in stats.by_hour.items():
            lines.append(f"  {hour}: {count}")
    if stats.notes:
        lines += ["", "备注："]
        lines += [f"  - {n}" for n in stats.notes]
    return "\n".join(lines)


__all__ = ["AuditStats", "compute_stats", "render"]
