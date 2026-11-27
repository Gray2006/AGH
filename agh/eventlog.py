"""事件日志与重放（D8）。

- 日志是哈希链：每条带前一条的哈希，改历史必然被检出。
- L1 状态机重放：把「记录下来的子级输出」按原顺序过状态机，每步状态摘要必须逐位一致。
- L2 重新执行：LLM 输出非确定，只要求统计一致（分布/均值在容差内）。

原规格要求 replay 与原运行一致，但 LLM 输出非确定 —— 所以必须分两级，不能只留一句「可重放」。
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .crypto import canonical_bytes


class LogTampered(Exception):
    pass


class LogUnreadable(LogTampered):
    """文件根本读不成日志（编码不对 / 不是文本）。

    继承 LogTampered 是为了让既有的 `except LogTampered` 调用点继续可用：
    对调用方来说结论一样——这份日志用不了，别崩，给个说法。
    """


@dataclass(frozen=True)
class LogEntry:
    seq: int
    ts: int
    type: str
    payload: dict[str, Any]
    prev_hash: str
    hash: str


def _entry_hash(seq: int, ts: int, type_: str, payload: dict, prev_hash: str) -> str:
    material = canonical_bytes(
        {"seq": seq, "ts": ts, "type": type_, "payload": payload, "prev": prev_hash}
    )
    return hashlib.sha256(material).hexdigest()


GENESIS = "0" * 64


def iter_entries(path: Path):
    """流式解析 JSONL 日志，逐条 yield LogEntry。解析失败抛 LogTampered。"""
    try:
        # utf-8-sig：接受普通 UTF-8，也接受记事本另存为加的 BOM。
        # BOM 是编码标记不是内容，不影响哈希链——不该让它看起来像「日志损坏」。
        text = Path(path).read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        # 用户常把「自己导出的原始日志」或别的工具的输出传进来。
        # AGH 日志固定 UTF-8，读不动就是选错文件了，不该甩 Python 堆栈。
        raise LogUnreadable(
            f"{path} 不是 UTF-8 编码，不像是 AGH 日志（AGH 日志固定 UTF-8）。"
            "如果你要导入别家的原始日志，用 `agh import --from-jsonl`"
        ) from exc
    except OSError as exc:
        raise LogUnreadable(f"无法读取 {path}：{exc}") from exc
    # 只按 \n 分：JSONL 的换行就是 \n，splitlines 会认 U+2028 等
    for lineno, line in enumerate(text.split("\n"), 1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
            yield LogEntry(
                seq=raw["seq"],
                ts=raw["ts"],
                type=raw["type"],
                payload=raw["payload"],
                prev_hash=raw["prev_hash"],
                hash=raw["hash"],
            )
        except (ValueError, KeyError, TypeError) as exc:
            raise LogTampered(f"日志格式损坏（第 {lineno} 条）：{exc}") from exc


class EventLog:
    def __init__(
        self,
        path: Path | None = None,
        clock: Callable[[], int] | None = None,
    ) -> None:
        self.path = Path(path) if path else None
        self._clock = clock or (lambda: int(time.time() * 1000))
        self.entries: list[LogEntry] = []
        if self.path and self.path.exists():
            self.entries = self.read()

    @property
    def last_hash(self) -> str:
        return self.entries[-1].hash if self.entries else GENESIS

    def append(self, type_: str, payload: dict[str, Any]) -> LogEntry:
        seq = len(self.entries) + 1
        ts = self._clock()
        prev = self.last_hash
        entry = LogEntry(
            seq=seq,
            ts=ts,
            type=type_,
            payload=payload,
            prev_hash=prev,
            hash=_entry_hash(seq, ts, type_, payload, prev),
        )
        self.entries.append(entry)
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(
                    json.dumps(
                        {
                            "seq": entry.seq,
                            "ts": entry.ts,
                            "type": entry.type,
                            "payload": entry.payload,
                            "prev_hash": entry.prev_hash,
                            "hash": entry.hash,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        return entry

    def stream(self):
        """逐条产出，不把整个日志留在内存里。大日志统计用这个。"""
        assert self.path is not None
        yield from iter_entries(self.path)

    def read(self) -> list[LogEntry]:
        assert self.path is not None
        return list(iter_entries(self.path))

    def head(self) -> str:
        """当前链头哈希（空日志返回 GENESIS）。"""
        return self.last_hash

    def size(self) -> int:
        return len(self.entries)

    def verify_against(self, expected_head: str, expected_size: int) -> None:
        """与外部记录的链头/长度比对：本地哈希链无法发现「截掉尾部」。"""
        self.verify()
        if self.size() != expected_size:
            raise LogTampered(f"长度不符: 期望 {expected_size}，实际 {self.size()}")
        if self.head() != expected_head:
            raise LogTampered("链头与外部记录不符（可能被截断或替换）")

    def verify(self) -> None:
        prev = GENESIS
        for i, entry in enumerate(self.entries, start=1):
            if entry.seq != i:
                raise LogTampered(f"序号断裂: 期望 {i}，得到 {entry.seq}")
            if entry.prev_hash != prev:
                raise LogTampered(f"链断裂于 seq={entry.seq}")
            expected = _entry_hash(
                entry.seq, entry.ts, entry.type, entry.payload, entry.prev_hash
            )
            if expected != entry.hash:
                raise LogTampered(f"内容被改动于 seq={entry.seq}")
            prev = entry.hash


def state_digest(state: Any) -> str:
    return hashlib.sha256(canonical_bytes(state)).hexdigest()


@dataclass
class ReplayReport:
    steps: int
    mismatches: list[int]
    digests: list[str]

    @property
    def bit_exact(self) -> bool:
        return not self.mismatches


class L1Replay:
    """状态机重放：必须逐位一致。"""

    def __init__(
        self,
        log: EventLog,
        reducer: Callable[[Any, LogEntry], Any],
        initial: Any,
    ) -> None:
        self.log = log
        self.reducer = reducer
        self.initial = initial

    def run(self) -> ReplayReport:
        state = self.initial
        digests: list[str] = []
        mismatches: list[int] = []
        for entry in self.log.entries:
            state = self.reducer(state, entry)
            digest = state_digest(state)
            digests.append(digest)
            recorded = entry.payload.get("state_digest")
            if recorded is not None and recorded != digest:
                mismatches.append(entry.seq)
        return ReplayReport(len(self.log.entries), mismatches, digests)


def l2_statistical_equivalence(
    run_a: list[float], run_b: list[float], tolerance: float = 0.05
) -> dict[str, Any]:
    """L2：重新执行只要求统计一致。"""
    if not run_a or not run_b:
        raise ValueError("两次运行都需要样本")
    mean_a = sum(run_a) / len(run_a)
    mean_b = sum(run_b) / len(run_b)
    var_a = sum((x - mean_a) ** 2 for x in run_a) / len(run_a)
    var_b = sum((x - mean_b) ** 2 for x in run_b) / len(run_b)
    return {
        "mean_a": mean_a,
        "mean_b": mean_b,
        "mean_delta": abs(mean_a - mean_b),
        "var_delta": abs(var_a - var_b),
        "within_tolerance": abs(mean_a - mean_b) <= tolerance,
    }
