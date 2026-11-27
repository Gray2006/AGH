"""审计会话：给多智能体流水线用的三行接入层。

    audit = AuditSession("run.jsonl")
    with audit:
        call_id = audit.call(model="deepseek-chat", prompt=p, response=r, tokens=312)
        audit.flag(call_id, reason="wrong")

记录进哈希链日志，事后可 `verify()`、`replay()`、`export()`。

产品面只暴露这一层：不需要理解契约、骨架、竞技场。进化那半在 `agh/lab` 之外，
消费的是这里导出的真实失败样本。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .crypto import sha256_hex
from .eventlog import EventLog


def _sha(text: str) -> str:
    return sha256_hex({"text": text})


@dataclass
class AuditSession:
    """一次运行的审计记录。

    `store_payload=False` 时只存输入输出的哈希，不存原文——适合敏感数据；
    代价是事后无法重放内容，只能验证「没被改过」。
    """

    path: str | Path
    label: str = ""
    store_payload: bool = True
    log: EventLog = field(init=False)
    _calls: dict[str, dict[str, Any]] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        self.path = Path(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.log = EventLog(self.path)
        self.log.append("session.start", {"label": self.label, "store_payload": self.store_payload})

    def __enter__(self) -> AuditSession:
        return self

    def __exit__(self, exc_type: Any, exc: Any, _tb: Any) -> None:
        self.log.append(
            "session.end",
            {"ok": exc_type is None, "error": None if exc is None else repr(exc)},
        )

    def call(
        self,
        *,
        model: str,
        prompt: str,
        response: str,
        tokens: int = 0,
        latency_ms: int = 0,
        category: str = "",
        ts: int | None = None,
        meta: dict[str, Any] | None = None,
    ) -> str:
        """记一次模型调用，返回 call_id（用于后续 flag）。

        `category` 是调用方自己给的分类（如「读取」「执行」「对话」），
        报告里可以按它筛选。留空表示未分类。

        `ts` 是毫秒时间戳，只在导入外部日志时给，用来保留原始发生时间；
        正常运行时留空，用写入时刻。
        """
        seq = sum(1 for e in self.log.entries if e.type == "llm.call")
        call_id = f"call-{sha256_hex({'p': prompt, 'r': response})[:12]}-{seq}"
        payload: dict[str, Any] = {
            "call_id": call_id,
            "model": model,
            "category": category,
            "tokens": tokens,
            "latency_ms": latency_ms,
            "prompt_sha256": _sha(prompt),
            "response_sha256": _sha(response),
            "meta": meta or {},
        }
        if self.store_payload:
            payload["prompt"] = prompt
            payload["response"] = response
        self.log.append("llm.call", payload, ts=ts)
        self._calls[call_id] = payload
        return call_id

    def flag(self, call_id: str, *, reason: str, note: str = "") -> None:
        """标记一次调用有问题。这是「产品反哺实验室」的入口。"""
        self.log.append("llm.flag", {"call_id": call_id, "reason": reason, "note": note})

    def note(self, kind: str, **payload: Any) -> None:
        self.log.append(kind, payload)

    def verify(self) -> bool:
        """校验哈希链。篡改/截断会抛 LogTampered。

        必须重读磁盘：内存里的 entries 是追加时就有的，篡改文件它察觉不到。
        """
        EventLog(Path(self.path)).verify()
        return True

    def replay(self) -> dict[str, Any]:
        """重读日志，逐条核对哈希，返回统计。"""
        fresh = EventLog(Path(self.path))
        fresh.verify()
        types: dict[str, int] = {}
        for entry in fresh.entries:
            types[entry.type] = types.get(entry.type, 0) + 1
        return {
            "entries": len(fresh.entries),
            "head": fresh.head(),
            "types": types,
        }

    def export(self, out: str | Path, *, redact: bool = False) -> Path:
        """导出审计包：日志事件 + 校验摘要。redact=True 时去掉原文。"""
        fresh = EventLog(Path(self.path))
        fresh.verify()
        events = []
        for entry in fresh.entries:
            payload = dict(entry.payload)
            if redact:
                payload.pop("prompt", None)
                payload.pop("response", None)
            events.append({"seq": entry.seq, "type": entry.type, "payload": payload})
        bundle = {
            "version": 1,
            "log": str(self.path),
            "head": fresh.head(),
            "entries": len(fresh.entries),
            "redacted": redact,
            "events": events,
        }
        path = Path(out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def summary(self) -> dict[str, Any]:
        calls = [e for e in self.log.entries if e.type == "llm.call"]
        flags = [e for e in self.log.entries if e.type == "llm.flag"]
        return {
            "calls": len(calls),
            "flags": len(flags),
            "tokens": sum(int(e.payload.get("tokens", 0)) for e in calls),
            "models": sorted({str(e.payload.get("model", "")) for e in calls}),
            "head": self.log.head(),
        }


def export_failures(
    log_path: str | Path, out: str | Path, *, include_payload: bool = True
) -> int:
    """从审计日志导出被标记的失败样本，供实验室消费。"""
    log = EventLog(Path(log_path))
    log.verify()
    calls = {
        e.payload["call_id"]: e.payload
        for e in log.entries
        if e.type == "llm.call" and "call_id" in e.payload
    }
    cases: list[dict[str, Any]] = []
    for entry in log.entries:
        if entry.type != "llm.flag":
            continue
        call = calls.get(entry.payload.get("call_id", ""))
        if call is None:
            continue
        case: dict[str, Any] = {
            "call_id": call["call_id"],
            "model": call.get("model", ""),
            "reason": entry.payload.get("reason", ""),
            "note": entry.payload.get("note", ""),
            "prompt_sha256": call.get("prompt_sha256", ""),
            "response_sha256": call.get("response_sha256", ""),
            "tokens": call.get("tokens", 0),
        }
        if include_payload and "prompt" in call:
            case["prompt"] = call["prompt"]
            case["response"] = call.get("response", "")
        cases.append(case)
    bundle = {"version": 1, "source": "audit", "cases": cases}
    path = Path(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(cases)


__all__ = ["AuditSession", "export_failures"]
