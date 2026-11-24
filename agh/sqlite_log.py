"""SQLite 版事件日志：长跑时比 JSONL 更适合查询与并发。

哈希链语义与 EventLog 一致：seq 连续、prev_hash 衔接、逐条校验。
"""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .eventlog import GENESIS, LogEntry, LogTampered, _entry_hash


class SqliteEventLog:
    def __init__(
        self,
        path: str | Path,
        clock: Callable[[], int] | None = None,
    ) -> None:
        self.path = Path(path)
        self._clock = clock or (lambda: int(time.time() * 1000))
        self._conn = sqlite3.connect(str(self.path))
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                seq INTEGER PRIMARY KEY,
                ts INTEGER NOT NULL,
                type TEXT NOT NULL,
                payload TEXT NOT NULL,
                prev_hash TEXT NOT NULL,
                hash TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def last_hash(self) -> str:
        row = self._conn.execute("SELECT hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
        return row[0] if row else GENESIS

    def size(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM events").fetchone()
        return int(row[0]) if row else 0

    def append(self, type_: str, payload: dict[str, Any]) -> LogEntry:
        seq = self.size() + 1
        ts = self._clock()
        prev = self.last_hash()
        digest = _entry_hash(seq, ts, type_, payload, prev)
        self._conn.execute(
            "INSERT INTO events (seq, ts, type, payload, prev_hash, hash) VALUES (?,?,?,?,?,?)",
            (seq, ts, type_, json.dumps(payload, ensure_ascii=False, sort_keys=True), prev, digest),
        )
        self._conn.commit()
        return LogEntry(seq=seq, ts=ts, type=type_, payload=payload, prev_hash=prev, hash=digest)

    def read(self) -> list[LogEntry]:
        rows = self._conn.execute(
            "SELECT seq, ts, type, payload, prev_hash, hash FROM events ORDER BY seq"
        ).fetchall()
        return [
            LogEntry(
                seq=row[0], ts=row[1], type=row[2], payload=json.loads(row[3]),
                prev_hash=row[4], hash=row[5],
            )
            for row in rows
        ]

    def verify(self) -> None:
        prev = GENESIS
        for index, entry in enumerate(self.read(), start=1):
            if entry.seq != index:
                raise LogTampered(f"序号断裂: 期望 {index}，得到 {entry.seq}")
            if entry.prev_hash != prev:
                raise LogTampered(f"链断裂于 seq={entry.seq}")
            expected = _entry_hash(entry.seq, entry.ts, entry.type, entry.payload, entry.prev_hash)
            if expected != entry.hash:
                raise LogTampered(f"哈希不符 seq={entry.seq}")
            prev = entry.hash

    def head(self) -> str:
        return self.last_hash()

    def verify_against(self, expected_head: str, expected_size: int) -> None:
        self.verify()
        if self.size() != expected_size:
            raise LogTampered(f"长度不符: 期望 {expected_size}，实际 {self.size()}")
        if self.head() != expected_head:
            raise LogTampered("链头与外部记录不符")


__all__ = ["SqliteEventLog"]
