"""把已有日志搬进 AGH 的可验证格式。

支持三种来源：
- generic：每行 {"model", "prompt", "response", "tokens"}
- langfuse：每行 {"type": "generation", "input", "output", "model", "usage"}
- langsmith：每行 {"run_type": "llm", "inputs": {"messages": [...]}, "outputs": {"messages": [...]}}

边界：导入是**事后记录**，不是原始签名的延续。它证明「这份日志从导入那一刻起没被改」，
不能证明「导入时那条记录本身没被改」。
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
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
    detected_format: str = "generic"

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "out": self.out,
            "imported": self.imported,
            "skipped": self.skipped,
            "log_head": self.log_head,
            "detected_format": self.detected_format,
        }


def _flatten(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    return json.dumps(value, ensure_ascii=False)


def _messages_text(value: Any) -> str:
    """从 LangSmith 的 {"messages": [...]} 里取出最后一条文本。"""
    if isinstance(value, dict) and isinstance(value.get("messages"), list):
        parts: list[str] = []
        for msg in value["messages"]:
            if isinstance(msg, dict):
                parts.append(_flatten(msg.get("content", msg.get("text", ""))))
            else:
                parts.append(_flatten(msg))
        return parts[-1] if parts else ""
    return _flatten(value)


def _tokens_from_usage(usage: Any) -> int:
    if not isinstance(usage, dict):
        return 0
    for key in ("total_tokens", "total"):
        value = usage.get(key)
        if isinstance(value, int):
            return value
    inp = usage.get("input", usage.get("prompt_tokens", 0)) or 0
    out = usage.get("output", usage.get("completion_tokens", 0)) or 0
    try:
        return int(inp) + int(out)
    except (TypeError, ValueError):
        return 0


def detect_format(sample: dict[str, Any]) -> str:
    if "run_type" in sample or ("inputs" in sample and "outputs" in sample):
        return "langsmith"
    if "trace_id" in sample or ("input" in sample and "output" in sample):
        return "langfuse"
    # OpenAI 的 chat completion 响应：choices[0].message.content
    if isinstance(sample.get("choices"), list) and sample["choices"]:
        return "openai"
    return "generic"


def _extract_langfuse(row: dict[str, Any]) -> tuple[str, str, str, int] | None:
    if row.get("type") not in (None, "generation", "event"):
        return None
    model = _flatten(row.get("model") or row.get("model_name") or "langfuse-unknown")
    prompt = _flatten(row.get("input"))
    response = _flatten(row.get("output"))
    if not prompt and not response:
        return None
    return model, prompt, response, _tokens_from_usage(row.get("usage"))


def _extract_openai(row: dict[str, Any]) -> tuple[str, str, str, int] | None:
    """OpenAI chat completion 响应（或带 messages 的请求）。"""
    choices = row.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    first = choices[0] if isinstance(choices[0], dict) else {}
    message = first.get("message") or {}
    response = _flatten(message.get("content") if isinstance(message, dict) else message)
    if not response:
        return None
    messages = row.get("messages")
    prompt = ""
    if isinstance(messages, list):
        parts = [
            _flatten(m.get("content"))
            for m in messages
            if isinstance(m, dict) and m.get("role") == "user"
        ]
        prompt = "\n".join(p for p in parts if p)
    model = _flatten(row.get("model") or "openai-unknown")
    return model, prompt, response, _tokens_from_usage(row.get("usage"))


def _extract_langsmith(row: dict[str, Any]) -> tuple[str, str, str, int] | None:
    if row.get("run_type") not in (None, "llm"):
        return None
    extra = row.get("extra") or {}
    metadata = extra.get("metadata") if isinstance(extra, dict) else None
    model = _flatten(
        (metadata or {}).get("ls_model_name")
        or (extra or {}).get("model")
        or row.get("model")
        or "langsmith-unknown"
    )
    prompt = _messages_text(row.get("inputs"))
    response = _messages_text(row.get("outputs"))
    if not prompt and not response:
        return None
    outputs = row.get("outputs")
    usage = outputs.get("token_usage") if isinstance(outputs, dict) else None
    return model, prompt, response, _tokens_from_usage(usage)


def _extract_generic(
    row: dict[str, Any], mapping: dict[str, str]
) -> tuple[str, str, str, int] | None:
    model = _flatten(row.get(mapping["model"]))
    prompt = _flatten(row.get(mapping["prompt"]))
    response = _flatten(row.get(mapping["response"]))
    if not model or (not prompt and not response):
        return None
    try:
        tokens = int(row.get(mapping["tokens"], 0) or 0)
    except (TypeError, ValueError):
        tokens = 0
    return model, prompt, response, tokens


def parse_map(pairs: list[str] | None) -> dict[str, str]:
    mapping = dict(DEFAULT_MAP)
    for pair in pairs or []:
        if "=" not in pair:
            raise ValueError(f"--map 需要 key=字段名，收到 {pair!r}")
        key, field = pair.split("=", 1)
        if key not in mapping:
            raise ValueError(f"未知字段 {key}，可用：{', '.join(mapping)}")
        mapping[key] = field
    return mapping


def import_any(
    source: str | Path,
    out: str | Path,
    *,
    fmt: str = "auto",
    mapping: Mapping[str, str] | None = None,
    label: str = "imported",
) -> ImportResult:
    """`fmt=auto` 时按第一行判断格式；判断不了按 generic 处理。"""
    src = Path(source)
    dst = Path(out)
    field_map = dict(DEFAULT_MAP if mapping is None else mapping)

    lines = [ln for ln in src.read_text(encoding="utf-8").split("\n") if ln.strip()]
    detected = fmt
    if fmt == "auto":
        detected = "generic"
        for line in lines:
            try:
                sample = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(sample, dict):
                detected = detect_format(sample)
                break

    extractors: dict[str, Callable[[dict[str, Any]], tuple[str, str, str, int] | None]] = {
        "langfuse": _extract_langfuse,
        "langsmith": _extract_langsmith,
        "openai": _extract_openai,
        "generic": lambda row: _extract_generic(row, field_map),
    }
    if detected not in extractors:
        raise ValueError(
            f"未知格式 {detected}，可用：auto / langfuse / langsmith / openai / generic"
        )
    extract = extractors[detected]

    if dst.exists():
        dst.unlink()
    audit = AuditSession(dst, label=label)
    imported = skipped = 0
    with audit:
        for lineno, line in enumerate(lines, 1):
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                skipped += 1
                continue
            if not isinstance(row, dict):
                skipped += 1
                continue
            parsed = extract(row)
            if parsed is None:
                skipped += 1
                continue
            model, prompt, response, tokens = parsed
            audit.call(
                model=model,
                prompt=prompt,
                response=response,
                tokens=tokens,
                meta={"source_line": lineno, "source_format": detected},
            )
            imported += 1

    return ImportResult(
        source=str(src),
        out=str(dst),
        imported=imported,
        skipped=skipped,
        log_head=audit.log.head(),
        detected_format=detected,
    )


# 兼容旧名字
def import_jsonl(
    source: str | Path, out: str | Path, *, mapping: Mapping[str, str] | None = None, label: str = "imported"
) -> ImportResult:
    return import_any(source, out, fmt="generic", mapping=mapping, label=label)


__all__ = [
    "DEFAULT_MAP",
    "ImportResult",
    "detect_format",
    "import_any",
    "import_jsonl",
    "parse_map",
]
