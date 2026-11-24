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

_CTRL = {c for c in range(0x20) if chr(c) not in "\n\t"}


def _clean(text: str, limit: int = 400) -> str:
    """去掉控制字符（NUL 等），并截断——note 是自由文本，可能被塞进原文。"""
    cleaned = "".join(ch for ch in str(text) if ord(ch) not in _CTRL)
    return cleaned if len(cleaned) <= limit else cleaned[:limit] + "…"


def _fence_for(text: str) -> str:
    """内容里已有 ``` 时，用更长的反引号围栏，避免把 markdown 结构撑破。"""
    longest = 0
    run = 0
    for ch in text:
        if ch == "`":
            run += 1
            longest = max(longest, run)
        else:
            run = 0
    return "`" * max(3, longest + 1)


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
            "reason": _clean(entry.payload.get("reason", ""), 120),
            "note": _clean(entry.payload.get("note", ""), 120),
            "prompt_sha256": call.get("prompt_sha256", "")[:16],
        }
        if with_payload:
            # 只去控制字符，不截断：带原文的目的就是完整复现
            row["prompt"] = _clean(call.get("prompt", ""), 200_000)
            row["response"] = _clean(call.get("response", ""), 200_000)
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
                prompt_text = str(row.get("prompt", ""))
                response_text = str(row.get("response", ""))
                fence = _fence_for(prompt_text + response_text)
                lines += [
                    f"<details><summary>样本 {i}：{row['reason']}</summary>",
                    "",
                    "输入：",
                    fence,
                    prompt_text,
                    fence,
                    "输出：",
                    fence,
                    response_text,
                    fence,
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
