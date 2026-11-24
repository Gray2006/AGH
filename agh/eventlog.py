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

    def read(self) -> list[LogEntry]:
        assert self.path is not None
        out: list[LogEntry] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            raw = json.loads(line)
            out.append(
                LogEntry(
                    seq=raw["seq"],
                    ts=raw["ts"],
                    type=raw["type"],
                    payload=raw["payload"],
                    prev_hash=raw["prev_hash"],
                    hash=raw["hash"],
                )
            )
        return out

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
