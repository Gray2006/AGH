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
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .audit import AuditSession
from .eventlog import EventLog, LogTampered

DEFAULT_MAP = {
    "model": "model",
    "prompt": "prompt",
    "response": "response",
    "tokens": "tokens",
    # 可选：调用方自带的分类（如「读取」「执行」「对话」）
    "category": "category",
    # 可选：原始发生时间（毫秒时间戳）。给了就不会被改写成导入时刻
    "ts": "ts",
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


def _parse_ts(value: Any) -> int | None:
    """把源数据的各种时间表示统一成毫秒时间戳。

    支持：毫秒整数、秒整数（< 1e11 视为秒）、ISO 8601 字符串、数字字符串。
    解析不了就返回 None（不猜），导入后就用写入时刻。
    """
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        num = float(value)
        return int(num * 1000) if num < 1e11 else int(num)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        secs: float | None
        try:
            secs = float(text)
        except ValueError:
            secs = None
        if secs is not None:
            return int(secs * 1000) if secs < 1e11 else int(secs)
        try:
            from datetime import datetime

            return int(datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp() * 1000)
        except ValueError:
            return None
    return None


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


def _read_source(src: Path) -> str:
    """读源日志，容忍真实世界里的编码。

    用户从别的工具导出的 jsonl 常见两种坑：
    - Windows 工具按 GBK 写（中文直接崩 UnicodeDecodeError）
    - 记事本另存为加了 UTF-8 BOM（第一行 JSON 解析失败，静默导入 0 条）

    utf-8-sig 同时处理 BOM 和普通 UTF-8；失败再试 GBK；都不行给明确提示，
    而不是把 Python 堆栈甩给用户。
    """
    raw = src.read_bytes()
    for encoding in ("utf-8-sig", "gbk"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError(
        f"源日志 {src} 既不是 UTF-8 也不是 GBK 编码，无法读取。"
        "请先转成 UTF-8 再导入，例如：iconv -f latin1 -t utf-8 源文件 > 新文件"
    )


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

    lines = [ln for ln in _read_source(src).split("\n") if ln.strip()]
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
    if mapping is not None and detected != "generic":
        # --map 只对 generic 生效；静默忽略会让用户以为字段映射已经应用
        raise ValueError(
            f"--map 只对 generic 格式生效，但检测到 {detected}。"
            "要按自定义字段导入，请加 --format generic"
        )
    extract = extractors[detected]

    # 先全部解析，再落盘：解析阶段失败不能动已有日志
    records: list[tuple[str, str, str, int, str, int | None, int]] = []
    skipped = 0
    cat_field = field_map.get("category") or ""
    ts_field = field_map.get("ts") or ""
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
        category = _flatten(row.get(cat_field)) if cat_field else ""
        ts = _parse_ts(row.get(ts_field)) if ts_field else None
        records.append((model, prompt, response, tokens, category, ts, lineno))

    if not records:
        # 一条都没导进来：保留原日志，返回 0 让调用方报错
        existing = ""
        if dst.exists():
            try:
                existing = EventLog(dst).head()
            except LogTampered:
                # 原日志本身已损坏：不阻止用户重导，但也不谎报链头
                existing = ""
        return ImportResult(
            source=str(src),
            out=str(dst),
            imported=0,
            skipped=skipped,
            log_head=existing,
            detected_format=detected,
        )

    # 写临时文件再原子替换：中途失败不会留下半份日志，也不会毁掉旧日志
    tmp = dst.with_name(f"{dst.name}.{os.getpid()}.tmp")
    try:
        audit = AuditSession(tmp, label=label)
        with audit:
            for model, prompt, response, tokens, category, ts, lineno in records:
                audit.call(
                    model=model,
                    prompt=prompt,
                    response=response,
                    tokens=tokens,
                    category=category,
                    ts=ts,
                    meta={"source_line": lineno, "source_format": detected},
                )
        os.replace(tmp, dst)
    finally:
        if tmp.exists():
            tmp.unlink()

    return ImportResult(
        source=str(src),
        out=str(dst),
        imported=len(records),
        skipped=skipped,
        log_head=audit.log.head(),
        detected_format=detected,
    )


# 兼容旧名字
def import_jsonl(
    source: str | Path, out: str | Path, *, mapping: Mapping[str, str] | None = None, label: str = "imported"
) -> ImportResult:
    # 用 auto 而不是写死 generic：否则 openai / langfuse 结构会被当成 generic 全部跳过
    return import_any(source, out, fmt="auto", mapping=mapping, label=label)


__all__ = [
    "DEFAULT_MAP",
    "ImportResult",
    "detect_format",
    "import_any",
    "import_jsonl",
    "parse_map",
]
