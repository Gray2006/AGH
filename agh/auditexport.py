"""把审计日志导出成 CSV，方便用 Excel / pandas 二次分析。

只导出元数据（call_id、模型、tokens、哈希、标记原因），不导出原文——
要原文用 `agh audit export-failures --with-payload` 或直接读 JSONL。
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any

from .eventlog import EventLog

FIELDS = [
    "call_id",
    "model",
    "tokens",
    "prompt_sha256",
    "response_sha256",
    "flagged",
    "flag_reason",
    "flag_note",
    "ts",
]


def export_csv(log_path: str | Path, out: str | Path | None = None) -> str:
    """返回 CSV 文本；给了 out 就同时写文件。"""
    path = Path(log_path)
    log = EventLog(path)
    log.verify()

    flags: dict[str, dict[str, Any]] = {}
    for entry in log.entries:
        if entry.type == "llm.flag":
            flags[str(entry.payload.get("call_id", ""))] = entry.payload

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    for entry in log.entries:
        if entry.type != "llm.call":
            continue
        payload = entry.payload
        call_id = str(payload.get("call_id", ""))
        flag = flags.get(call_id)
        writer.writerow(
            {
                "call_id": call_id,
                "model": payload.get("model", ""),
                "tokens": payload.get("tokens", 0),
                "prompt_sha256": payload.get("prompt_sha256", ""),
                "response_sha256": payload.get("response_sha256", ""),
                "flagged": "yes" if flag else "no",
                "flag_reason": (flag or {}).get("reason", ""),
                "flag_note": (flag or {}).get("note", ""),
                "ts": entry.ts,
            }
        )

    text = buf.getvalue()
    if out is not None:
        target = Path(out)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return text


def export_jsonl_hash_only(log_path: str | Path, out: str | Path) -> int:
    """导出「只有哈希」的版本：去掉 prompt/response 原文，保留结构。

    给需要共享日志但不想泄露内容的人用。
    """
    path = Path(log_path)
    log = EventLog(path)
    log.verify()
    lines: list[str] = []
    for entry in log.entries:
        payload = dict(entry.payload)
        payload.pop("prompt", None)
        payload.pop("response", None)
        lines.append(
            __import__("json").dumps(
                {
                    "seq": entry.seq,
                    "ts": entry.ts,
                    "type": entry.type,
                    "payload": payload,
                    "prev_hash": entry.prev_hash,
                    "hash": entry.hash,
                },
                ensure_ascii=False,
            )
        )
    target = Path(out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(lines)


__all__ = ["FIELDS", "export_csv", "export_jsonl_hash_only"]
