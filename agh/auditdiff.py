"""比较两份审计日志：哪次调用是新的、哪次消失了、统计怎么变。"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .eventlog import EventLog


@dataclass(frozen=True)
class LogDiff:
    a: str
    b: str
    only_a: tuple[str, ...]
    only_b: tuple[str, ...]
    common: int
    stats_a: dict[str, Any]
    stats_b: dict[str, Any]
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "a": self.a,
            "b": self.b,
            "only_a": list(self.only_a),
            "only_b": list(self.only_b),
            "common": self.common,
            "stats_a": self.stats_a,
            "stats_b": self.stats_b,
            "notes": list(self.notes),
        }


def _calls(path: Path) -> dict[str, dict[str, Any]]:
    log = EventLog(path)
    log.verify()
    out: dict[str, dict[str, Any]] = {}
    for entry in log.entries:
        if entry.type == "llm.call":
            out[entry.payload.get("call_id", "")] = dict(entry.payload)
    return out


def _stats(calls: dict[str, dict[str, Any]]) -> dict[str, Any]:
    models: dict[str, int] = {}
    tokens = 0
    for call in calls.values():
        model = str(call.get("model", ""))
        models[model] = models.get(model, 0) + 1
        with contextlib.suppress(TypeError, ValueError):
            tokens += int(call.get("tokens", 0) or 0)
    return {"calls": len(calls), "tokens": tokens, "models": models}


def _changed(before: dict[str, Any], after: dict[str, Any]) -> bool:
    """同一条 call_id 在两次日志里是否真的指向同一次调用。

    只看会改变结论的字段：模型、token、输入输出哈希。
    timestamp / latency 天然会变，不能算差异。
    """
    keys = ("model", "tokens", "prompt_sha256", "response_sha256")
    return any(before.get(key) != after.get(key) for key in keys)


def diff_logs(a: str | Path, b: str | Path) -> LogDiff:
    path_a, path_b = Path(a), Path(b)
    calls_a = _calls(path_a)
    calls_b = _calls(path_b)

    ids_a, ids_b = set(calls_a), set(calls_b)
    only_a = tuple(sorted(ids_a - ids_b))
    only_b = tuple(sorted(ids_b - ids_a))
    shared = ids_a & ids_b
    common = len(shared)

    notes: list[str] = []
    stats_a, stats_b = _stats(calls_a), _stats(calls_b)
    if stats_b["calls"] > stats_a["calls"]:
        notes.append(f"b 比 a 多 {stats_b['calls'] - stats_a['calls']} 次调用")
    if stats_b["tokens"] != stats_a["tokens"]:
        notes.append(f"tokens 变化 {stats_b['tokens'] - stats_a['tokens']:+d}")
    if ids_a and len(only_a) == len(ids_a):
        notes.append("a 的记录在 b 里全部消失（可能是重新导入或换了日志）")

    # call_id 只由 prompt/response 内容 + 序号决定，不含模型。
    # 同样的输入换模型跑，id 不变但实际是不同的一次调用——diff 必须说出来。
    changed = [cid for cid in sorted(shared) if _changed(calls_a[cid], calls_b[cid])]
    for cid in changed[:5]:
        before = calls_a[cid].get("model", "")
        after = calls_b[cid].get("model", "")
        if before != after:
            notes.append(f"{cid} 的模型不同：{before} → {after}")
        else:
            notes.append(f"{cid} 的内容不同（同 id 不同 payload）")
    if len(changed) > 5:
        notes.append(f"……另有 {len(changed) - 5} 条同 id 记录内容不同")

    return LogDiff(
        a=str(path_a),
        b=str(path_b),
        only_a=only_a,
        only_b=only_b,
        common=common,
        stats_a=stats_a,
        stats_b=stats_b,
        notes=notes,
    )


__all__ = ["LogDiff", "diff_logs"]
