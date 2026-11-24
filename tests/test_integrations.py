from __future__ import annotations

import json
from pathlib import Path

import pytest

from agh.bus import Event, SubjectConflict
from agh.bus_nats import NatsBus
from agh.costs import Price, usage_to_budget
from agh.eventlog import EventLog, LogTampered
from agh.sqlite_log import SqliteEventLog


def test_usage_to_budget() -> None:
    budget = usage_to_budget(
        {"prompt_tokens": 1_000_000, "completion_tokens": 500_000},
        price=Price(0.28, 1.10),
    )
    assert budget.usd == pytest.approx(0.28 + 0.55)
    assert budget.compute_units == pytest.approx(1500.0)


def test_usage_zero() -> None:
    assert usage_to_budget(None).usd == 0.0


class FakeAck:
    def __init__(self, seq: int) -> None:
        self.seq = seq


class FakeMsg:
    def __init__(self, data: bytes, seq: int) -> None:
        self.data = data
        self.metadata = type("M", (), {"sequence": {"stream": seq}})()
        self.acked = False

    def ack(self) -> None:
        self.acked = True

    def nak(self) -> None:
        pass


class FakeSub:
    def __init__(self, msgs: list[FakeMsg]) -> None:
        self._msgs = msgs

    def fetch(self, count: int, timeout: float = 1) -> list[FakeMsg]:
        return self._msgs[:count]


class FakeJS:
    def __init__(self) -> None:
        self.published: list[tuple[str, bytes, dict]] = []
        self.msgs: list[FakeMsg] = []

    def publish(self, subject: str, payload: bytes, headers: dict | None = None):
        if headers and headers.get("Nats-Expected-Last-Subject-Sequence") == "99":
            raise RuntimeError("wrong expected last sequence")
        self.published.append((subject, payload, headers or {}))
        return FakeAck(seq=len(self.published))

    def pull_subscribe(self, subject: str, durable: str):
        return FakeSub(self.msgs)


def test_nats_publish_headers_and_conflict() -> None:
    js = FakeJS()
    bus = NatsBus(js)
    seq = bus.publish("jobs", Event(event_id="e1", type="t", payload={"a": 1}), expected_last_seq=1)
    assert seq == 1
    subject, payload, headers = js.published[0]
    assert subject == "agh.jobs"
    assert headers["Nats-Msg-Id"] == "e1"
    assert headers["Nats-Expected-Last-Subject-Sequence"] == "1"
    assert json.loads(payload.decode())["id"] == "e1"
    with pytest.raises(SubjectConflict):
        bus.publish("jobs", Event(event_id="e2", type="t", payload={}), expected_last_seq=99)


def test_nats_fetch_and_ack() -> None:
    js = FakeJS()
    bus = NatsBus(js)
    js.msgs = [FakeMsg(json.dumps({"id": "e1", "type": "t", "payload": {"n": 1}}).encode(), 7)]
    deliveries = bus.fetch("jobs", "w", 5)
    assert len(deliveries) == 1
    assert deliveries[0].seq == 7
    bus.ack(deliveries[0])
    assert js.msgs[0].acked


def test_sqlite_log_chain_and_truncation(tmp_path: Path) -> None:
    log = SqliteEventLog(tmp_path / "e.db")
    for i in range(3):
        log.append("t", {"i": i})
    head, size = log.head(), log.size()
    log.verify()
    # 删除最后一条，本地链仍然自洽
    log._conn.execute("DELETE FROM events WHERE seq = 3")
    log._conn.commit()
    log.verify()
    with pytest.raises(LogTampered):
        log.verify_against(head, size)
    log.close()


def test_sqlite_matches_jsonl_semantics(tmp_path: Path) -> None:
    a = EventLog(tmp_path / "a.jsonl", clock=lambda: 1)
    b = SqliteEventLog(tmp_path / "b.db", clock=lambda: 1)
    for i in range(3):
        a.append("t", {"i": i})
        b.append("t", {"i": i})
    assert [e.hash for e in a.read()] == [e.hash for e in b.read()]
    b.close()
