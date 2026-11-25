"""NATS JetStream 适配器：把 Bus 协议落到真实语义上。

不绑定 nats-py 的导入——客户端对象由调用方注入，便于测试与版本隔离。
实现的语义（与 docs/verification-nats.md 一致）：

- 发布端按 Nats-Msg-Id 去重，窗口由 stream 配置（默认 2 分钟），不是永久；
- 投递是 at-least-once，消费端必须幂等；
- 期望序号用 Nats-Expected-Last-Subject-Sequence 头做乐观并发；
- ack 超时服务端会重投，MaxDeliver 默认无限。

这里的客户端接口（鸭子类型）：
    js.publish(subject, payload, headers=...) -> ack 对象（含 .stream, .seq, .duplicate）
    js.pull_subscribe(subject, durable) -> 订阅对象（fetch/ack/nak）
"""

from __future__ import annotations

import inspect
import json
from dataclasses import dataclass
from typing import Any, Protocol

from .bus import Delivery, Event, SubjectConflict


class JetStreamLike(Protocol):
    def publish(self, subject: str, payload: bytes, headers: dict[str, str] | None = None) -> Any: ...

    def pull_subscribe(self, subject: str, _durable: str) -> Any: ...


@dataclass
class NatsDelivery:
    """把 NATS 消息包成 Delivery，保留 ack 能力。"""

    stream: str
    consumer: str
    seq: int
    event: Event
    attempts: int
    delivered_at_ms: int
    raw: Any = None

    def ack(self) -> None:
        if self.raw is not None:
            self.raw.ack()

    def nak(self) -> None:
        if self.raw is not None:
            self.raw.nak()


class NatsBus:
    def __init__(self, js: JetStreamLike, *, subject_prefix: str = "agh") -> None:
        self.js = js
        self.subject_prefix = subject_prefix
        self._subs: dict[tuple[str, str], Any] = {}

    def _subject(self, stream: str) -> str:
        return f"{self.subject_prefix}.{stream}"

    def _payload(self, event: Event) -> bytes:
        return json.dumps(
            {"id": event.event_id, "type": event.type, "payload": event.payload}
        ).encode()

    def _headers(self, event: Event, expected_last_seq: int | None) -> dict[str, str]:
        headers = {"Nats-Msg-Id": event.event_id}
        if expected_last_seq is not None:
            headers["Nats-Expected-Last-Subject-Sequence"] = str(expected_last_seq)
        return headers

    def publish(
        self,
        stream: str,
        event: Event,
        expected_last_seq: int | None = None,
    ) -> int:
        """同步接口。nats-py 的 JetStream.publish 是 async，请用 publish_async。"""
        try:
            ack = self.js.publish(
                self._subject(stream),
                self._payload(event),
                headers=self._headers(event, expected_last_seq),
            )
        except Exception as exc:  # 服务端明确拒绝时由客户端抛错
            if "expected" in str(exc).lower():
                raise SubjectConflict(str(exc)) from exc
            raise
        if inspect.isawaitable(ack):
            ack.close()  # type: ignore[attr-defined]
            raise TypeError(
                "NatsBus.publish 是同步接口，但客户端返回了 awaitable；"
                "nats-py 请用 await bus.publish_async(...)"
            )
        return int(getattr(ack, "seq", 0))

    async def publish_async(
        self,
        stream: str,
        event: Event,
        expected_last_seq: int | None = None,
    ) -> int:
        try:
            ack = await self.js.publish(
                self._subject(stream),
                self._payload(event),
                headers=self._headers(event, expected_last_seq),
            )
        except Exception as exc:
            if "expected" in str(exc).lower():
                raise SubjectConflict(str(exc)) from exc
            raise
        return int(getattr(ack, "seq", 0))

    def subscribe(self, stream: str, consumer: str) -> None:
        key = (stream, consumer)
        if key not in self._subs:
            self._subs[key] = self.js.pull_subscribe(self._subject(stream), durable=consumer)

    def fetch(self, stream: str, consumer: str, max_msgs: int = 10) -> list[Delivery]:
        """同步接口；nats-py 的 fetch 是 async，请用 fetch_async。"""
        self.subscribe(stream, consumer)
        sub = self._subs[(stream, consumer)]
        msgs = sub.fetch(max_msgs, timeout=1)
        if inspect.isawaitable(msgs):
            msgs.close()  # type: ignore[attr-defined]
            raise TypeError(
                "NatsBus.fetch 是同步接口，但客户端返回了 awaitable；"
                "nats-py 请用 await bus.fetch_async(...)"
            )
        return self._to_deliveries(stream, consumer, msgs)

    async def fetch_async(
        self, stream: str, consumer: str, max_msgs: int = 10
    ) -> list[Delivery]:
        self.subscribe(stream, consumer)
        sub = self._subs[(stream, consumer)]
        msgs = await sub.fetch(max_msgs, timeout=1)
        return self._to_deliveries(stream, consumer, msgs)

    def _to_deliveries(self, stream: str, consumer: str, msgs: Any) -> list[Delivery]:
        out: list[Delivery] = []  # type: ignore[assignment]
        for msg in msgs:
            data = json.loads(msg.data.decode())
            seq = int(getattr(msg.metadata, "sequence", {}).get("stream", 0)) if hasattr(msg, "metadata") else 0
            event = Event(event_id=data["id"], type=data["type"], payload=data["payload"])
            out.append(  # type: ignore[arg-type]
                NatsDelivery(
                    stream=stream,
                    consumer=consumer,
                    seq=seq,
                    event=event,
                    attempts=1,
                    delivered_at_ms=0,
                    raw=msg,
                )
            )
        return out

    def ack(self, delivery: Delivery) -> None:
        if isinstance(delivery, NatsDelivery):
            delivery.ack()

    def nack(self, delivery: Delivery) -> None:
        if isinstance(delivery, NatsDelivery):
            delivery.nak()


__all__ = ["JetStreamLike", "NatsBus", "NatsDelivery"]
