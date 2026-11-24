"""把已有日志搬进 AGH 的可验证格式。

适用场景：你已经在别处记了模型调用（自己的 jsonl、LangSmith 导出、脚本日志），
想把它们变成可校验、可重放的审计日志。

边界要说清楚：导入是**事后记录**，不是原始签名的延续。它能证明「这份日志从导入那一刻起没被改」，
不能证明「导入时那条记录本身没被改」。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .audit import AuditSession

DEFAULT_MAP = {
    "model": "model",
    "prompt": "prompt",
    "response": "response",
    "tokens": "tokens",
}


@dataclass(frozen=True)
class ImportResult:
    source: str
    out: str
    imported: int
    skipped: int
    log_head: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "out": self.out,
            "imported": self.imported,
            "skipped": self.skipped,
            "log_head": self.log_head,
        }


def _parse_map(pairs: list[str] | None) -> dict[str, str]:
    mapping = dict(DEFAULT_MAP)
    for pair in pairs or []:
        if "=" not in pair:
            raise ValueError(f"--map 需要 key=字段名，收到 {pair!r}")
        key, field = pair.split("=", 1)
        if key not in mapping:
            raise ValueError(f"未知字段 {key}，可用：{', '.join(mapping)}")
        mapping[key] = field
    return mapping


def import_jsonl(
    source: str | Path,
    out: str | Path,
    *,
    mapping: Mapping[str, str] | None = None,
    label: str = "imported",
) -> ImportResult:
    """逐行读源 jsonl，写成 AGH 审计日志。缺 model/prompt/response 的行会跳过。"""
    src = Path(source)
    dst = Path(out)
    field_map = dict(DEFAULT_MAP if mapping is None else mapping)

    imported = 0
    skipped = 0
    # 覆盖而不是追加：重复导入同一份源，不应产生重复条目
    if dst.exists():
        dst.unlink()
    audit = AuditSession(dst, label=label)
    with audit:
        for lineno, line in enumerate(src.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                skipped += 1
                continue
            if not isinstance(row, dict):
                skipped += 1
                continue
            model = str(row.get(field_map["model"], "") or "")
            prompt = row.get(field_map["prompt"])
            response = row.get(field_map["response"])
            if not model or prompt is None or response is None:
                skipped += 1
                continue
            tokens = row.get(field_map["tokens"], 0)
            try:
                token_count = int(tokens or 0)
            except (TypeError, ValueError):
                token_count = 0
            audit.call(
                model=model,
                prompt=str(prompt),
                response=str(response),
                tokens=token_count,
                meta={"source_line": lineno},
            )
            imported += 1
    return ImportResult(
        source=str(src),
        out=str(dst),
        imported=imported,
        skipped=skipped,
        log_head=audit.log.head(),
    )


def parse_map(pairs: list[str] | None) -> dict[str, str]:
    return _parse_map(pairs)


__all__ = ["DEFAULT_MAP", "ImportResult", "import_jsonl", "parse_map"]
