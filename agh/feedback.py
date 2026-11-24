"""把一次审计日志整理成可直接粘贴到 GitHub issue 的反馈。

默认脱敏：只带哈希、模型名、标记原因，**不带输入输出原文**。
用户要带原文时显式加 `--with-payload`。
"""

from __future__ import annotations

import platform
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .audit import AuditSession
from .eventlog import EventLog


def _session_summary(log_path: Path) -> dict[str, Any]:
    audit = AuditSession.__new__(AuditSession)
    audit.path = log_path
    audit.log = EventLog(log_path)
    return audit.summary()


def _flagged(log_path: Path, *, with_payload: bool) -> list[dict[str, Any]]:
    log = EventLog(log_path)
    calls = {
        e.payload["call_id"]: e.payload
        for e in log.entries
        if e.type == "llm.call" and "call_id" in e.payload
    }
    rows: list[dict[str, Any]] = []
    for entry in log.entries:
        if entry.type != "llm.flag":
            continue
        call = calls.get(entry.payload.get("call_id", ""), {})
        row: dict[str, Any] = {
            "call_id": entry.payload.get("call_id", ""),
            "model": call.get("model", ""),
            "reason": entry.payload.get("reason", ""),
            "note": entry.payload.get("note", ""),
            "prompt_sha256": call.get("prompt_sha256", "")[:16],
        }
        if with_payload:
            row["prompt"] = call.get("prompt", "")
            row["response"] = call.get("response", "")
        rows.append(row)
    return rows


def build_feedback(log_path: str | Path, *, with_payload: bool = False) -> str:
    path = Path(log_path)
    EventLog(path).verify()  # 日志被改过就别拿去反馈，先让人修
    summary = _session_summary(path)
    rows = _flagged(path, with_payload=with_payload)

    lines = [
        "## AGH 反馈",
        "",
        f"- 版本：{__version__}",
        f"- Python：{sys.version.split()[0]}",
        f"- 平台：{platform.system()}-{platform.release()}",
        f"- 调用：{summary['calls']} 次，token {summary['tokens']}",
        f"- 标记：{summary['flags']} 次",
        f"- 链头：`{summary['head'][:16]}`",
        "",
    ]
    if rows:
        lines += [
            "### 被标记的调用（默认脱敏，只有哈希）" if not with_payload else "### 被标记的调用",
            "",
            "| call_id | model | reason | note | prompt_sha256 |",
            "|---|---|---|---|---|",
        ]
        for row in rows[:10]:
            lines.append(
                f"| {row['call_id']} | {row['model']} | {row['reason']} | "
                f"{row['note']} | {row['prompt_sha256']} |"
            )
        if len(rows) > 10:
            lines.append(f"| … | 还有 {len(rows) - 10} 条 | | | |")
        lines.append("")
        if with_payload:
            for i, row in enumerate(rows[:5], 1):
                lines += [
                    f"<details><summary>样本 {i}：{row['reason']}</summary>",
                    "",
                    "输入：",
                    "```",
                    str(row.get("prompt", "")),
                    "```",
                    "输出：",
                    "```",
                    str(row.get("response", "")),
                    "```",
                    "</details>",
                    "",
                ]
    else:
        lines += ["_没有标记过的调用。_", ""]

    lines += [
        "### 复现步骤",
        "",
        "（请补充）",
        "",
        "### 期望行为 / 实际行为",
        "",
        "（请补充）",
        "",
        "---",
        "",
        "脱敏说明：默认只带输入输出的 sha256 前缀，不含原文。"
        "需要带原文时用 `agh feedback --log ... --with-payload`，并在提交前自己检查一遍。",
    ]
    return "\n".join(lines)


__all__ = ["build_feedback"]
