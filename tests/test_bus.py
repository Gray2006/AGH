"""主题总线测试 —— 本地实现，验证与 NATS JetStream 语义等价的部分。

NATS 实际是 at-least-once + 发布端窗口去重 + 消费端幂等，不是 exactly-once。
"""

from __future__ import annotations

import pytest

from agh.bus import BusApplication, Event, InProcBus, SubjectConflict


class Clock:
    def __init__(self) -> None:
        self.now = 0

    def __call__(self) -> int:
        return self.now

    def advance(self, ms: int) -> None:
        self.now += ms


def ev(eid: str, n: int = 1) -> Event:
    return Event(event_id=eid, type="job", payload={"n": n})


def test_publish_and_fetch_in_order() -> None:
    bus = InProcBus()
    bus.publish("jobs", ev("e1", 1))
    bus.publish("jobs", ev("e2", 2))
    bus.subscribe("jobs", "worker")
    deliveries = bus.fetch("jobs", "worker", max_msgs=10)
    assert [d.event.payload["n"] for d in deliveries] == [1, 2]
    assert [d.seq for d in deliveries] == [1, 2]


def test_duplicate_event_id_deduped_at_publish() -> None:
    bus = InProcBus(dedup_window=100)
    first = bus.publish("jobs", ev("m-1"))
    second = bus.publish("jobs", ev("m-1"))
    assert first == second == 1
    bus.subscribe("jobs", "w")
    assert len(bus.fetch("jobs", "w", max_msgs=10)) == 1
    assert bus.stats.duplicates_published == 1


def test_dedup_window_expires() -> None:
    bus = InProcBus(dedup_window=1)
    first = bus.publish("jobs", ev("m-1"))
    bus.publish("jobs", ev("m-2"))  # 挤出 m-1
    third = bus.publish("jobs", ev("m-1"))
    assert first == 1 and third == 3


def test_expected_last_seq_conflict() -> None:
    bus = InProcBus()
    bus.publish("jobs", ev("e1"))
    with pytest.raises(SubjectConflict):
        bus.publish("jobs", ev("e2"), expected_last_seq=0)
    assert bus.stats.conflicts == 1
    bus.publish("jobs", ev("e2"), expected_last_seq=1)


def test_batch_is_atomic_and_contiguous() -> None:
    bus = InProcBus()
    seqs = bus.publish_batch("jobs", [ev("a"), ev("b"), ev("c")])
    assert seqs == [1, 2, 3]
    bus.subscribe("jobs", "w")
    assert [d.seq for d in bus.fetch("jobs", "w", 10)] == [1, 2, 3]


def test_batch_rejects_internal_duplicate() -> None:
    bus = InProcBus()
    with pytest.raises(ValueError):
        bus.publish_batch("jobs", [ev("a"), ev("a")])
    assert bus.last_seq("jobs") == 0


def test_ack_timeout_redelivers() -> None:
    clock = Clock()
    bus = InProcBus(clock=clock, ack_wait_ms=5_000)
    bus.publish("jobs", ev("e1", 7))
    bus.subscribe("jobs", "w")
    first = bus.fetch("jobs", "w", 1)
    assert len(first) == 1
    clock.advance(6_000)
    second = bus.fetch("jobs", "w", 1)
    assert len(second) == 1
    assert second[0].event.event_id == "e1"
    assert second[0].attempts == 2
    assert bus.stats.redelivered == 1


def test_consumer_idempotent_across_redelivery() -> None:
    clock = Clock()
    bus = InProcBus(clock=clock, ack_wait_ms=100)
    bus.publish("jobs", ev("e1"))
    bus.subscribe("jobs", "w")
    bus.fetch("jobs", "w", 1)  # 假装消费失败，不 ack
    clock.advance(200)
    seen: list[str] = []
    app = BusApplication(bus, "jobs", "w")
    handled = app.run(lambda e: seen.append(e.event_id), max_msgs=10)
    assert handled == 1
    clock.advance(200)
    handled_again = app.run(lambda e: seen.append(e.event_id), max_msgs=10)
    assert handled_again == 0
    assert seen == ["e1"]


def test_nack_requeues_immediately() -> None:
    clock = Clock()
    bus = InProcBus(clock=clock, ack_wait_ms=10**6)
    bus.publish("jobs", ev("e1"))
    bus.subscribe("jobs", "w")
    d = bus.fetch("jobs", "w", 1)[0]
    bus.nack(d)
    again = bus.fetch("jobs", "w", 1)
    assert again and again[0].seq == 1
