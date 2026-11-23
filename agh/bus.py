"""总线（D9 / §3.5）：有效一次 = 去重 + 幂等 + 期望序号。

抽象 Bus 接口 → 阶段 0 用进程内实现，NATS/JetStream 后接为适配器。
这里刻意不做「exactly-once」的假承诺，只给三样东西：
1. 发布端 event_id 去重（对应 Nats-Msg-Id 语义）；
2. 消费端幂等（重复投递不产生第二次副作用）；
3. 乐观并发（期望序号）。

ack 超时重投递是 NATS 的真实行为，本实现也模拟：超时后消息重新可见，
所以「至少一次」交付必须靠幂等兜住。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, Sequence

from pydantic import BaseModel, ConfigDict, Field


class SubjectConflict(Exception):
    """期望序号不匹配（乐观并发失败）。"""


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str = Field(min_length=1)
    type: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)


@dataclass
class Delivery:
    stream: str
    consumer: str
    seq: int
    event: Event
    attempts: int = 1
    delivered_at_ms: int = 0


@dataclass
class _Consumer:
    next_index: int = 0
    pending: dict[int, Delivery] = field(default_factory=dict)


@dataclass
class BusStats:
    published: int = 0
    duplicates_published: int = 0
    redelivered: int = 0
    conflicts: int = 0
    acked: int = 0


class Bus(Protocol):
    def publish(
        self, stream: str, event: Event, expected_last_seq: int | None = None
    ) -> int: ...

    def publish_batch(
        self,
        stream: str,
        events: Sequence[Event],
        expected_last_seq: int | None = None,
    ) -> list[int]: ...

    def subscribe(self, stream: str, consumer: str) -> None: ...

    def fetch(self, stream: str, consumer: str, max_msgs: int = 10) -> list[Delivery]: ...

    def ack(self, delivery: Delivery) -> None: ...


class InProcBus:
    """进程内总线。去重窗口按「条数」而不是时间，保证测试确定性。"""

    def __init__(
        self,
        clock: Callable[[], int] | None = None,
        ack_wait_ms: int = 5_000,
        dedup_window: int = 1_000,
    ) -> None:
        self._clock = clock or (lambda: int(time.time() * 1000))
        self.ack_wait_ms = ack_wait_ms
        self.dedup_window = dedup_window
        self._streams: dict[str, list[Event]] = {}
        self._dedup: dict[str, dict[str, int]] = {}
        self._consumers: dict[tuple[str, str], _Consumer] = {}
        self.stats = BusStats()

    def last_seq(self, stream: str) -> int:
        return len(self._streams.get(stream, []))

    # ---------------------------------------------------------------- 发布
    def publish(
        self, stream: str, event: Event, expected_last_seq: int | None = None
    ) -> int:
        return self.publish_batch(stream, [event], expected_last_seq)[0]

    def publish_batch(
        self,
        stream: str,
        events: Sequence[Event],
        expected_last_seq: int | None = None,
    ) -> list[int]:
        if not events:
            return []
        ids = [e.event_id for e in events]
        if len(set(ids)) != len(ids):
            raise ValueError("同一批次内 event_id 重复")
        actual = self.last_seq(stream)
        if expected_last_seq is not None and expected_last_seq != actual:
            self.stats.conflicts += 1
            raise SubjectConflict(f"{stream}: 期望 {expected_last_seq}，实际 {actual}")

        log = self._streams.setdefault(stream, [])
        window = self._dedup.setdefault(stream, {})
        seqs: list[int] = []
        fresh: list[Event] = []
        for e in events:
            if e.event_id in window:
                self.stats.duplicates_published += 1
                seqs.append(window[e.event_id])
            else:
                fresh.append(e)
        # 原子批量：校验全做完再落盘
        for e in fresh:
            log.append(e)
            seq = len(log)
            window[e.event_id] = seq
            if len(window) > self.dedup_window:
                oldest = next(iter(window))
                del window[oldest]
            self.stats.published += 1
        # 返回顺序与入参一致
        result: list[int] = []
        for e in events:
            result.append(window[e.event_id])
        return result

    # ---------------------------------------------------------------- 订阅
    def subscribe(self, stream: str, consumer: str) -> None:
        self._consumers.setdefault((stream, consumer), _Consumer())

    def fetch(self, stream: str, consumer: str, max_msgs: int = 10) -> list[Delivery]:
        self.subscribe(stream, consumer)
        state = self._consumers[(stream, consumer)]
        log = self._streams.get(stream, [])
        now = self._clock()
        out: list[Delivery] = []
        for seq, d in list(state.pending.items()):
            if len(out) >= max_msgs:
                break
            if now - d.delivered_at_ms >= self.ack_wait_ms:
                d.attempts += 1
                d.delivered_at_ms = now
                out.append(d)
                self.stats.redelivered += 1
        while len(out) < max_msgs and state.next_index < len(log):
            seq = state.next_index + 1
            state.next_index += 1
            d = Delivery(
                stream=stream,
                consumer=consumer,
                seq=seq,
                event=log[seq - 1],
                delivered_at_ms=now,
            )
            state.pending[seq] = d
            out.append(d)
        return out

    def ack(self, delivery: Delivery) -> None:
        state = self._consumers.get((delivery.stream, delivery.consumer))
        if state is None:
            raise KeyError(f"未订阅: {delivery.stream}/{delivery.consumer}")
        state.pending.pop(delivery.seq, None)
        self.stats.acked += 1

    def nack(self, delivery: Delivery) -> None:
        """拒绝：立即可重投（不必等 ack 超时）。"""
        state = self._consumers.get((delivery.stream, delivery.consumer))
        if state is not None and delivery.seq in state.pending:
            state.pending[delivery.seq].delivered_at_ms = -10**12


class BusApplication:
    """幂等消费：event_id 记过之后重复投递直接跳过。"""

    def __init__(self, bus: Bus, stream: str, consumer: str) -> None:
        self.bus = bus
        self.stream = stream
        self.consumer = consumer
        self.processed: dict[str, int] = {}

    def run(self, handler: Callable[[Event], None], max_msgs: int = 100) -> int:
        handled = 0
        for d in self.bus.fetch(self.stream, self.consumer, max_msgs):
            if d.event.event_id in self.processed:
                self.bus.ack(d)
                continue
            handler(d.event)
            self.processed[d.event.event_id] = d.seq
            handled += 1
            self.bus.ack(d)
        return handled
