"""NATS 联调：需要 docker compose up -d nats 后设置 NATS_URL 才跑。"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(not os.environ.get("NATS_URL"), reason="未设置 NATS_URL")


def test_nats_roundtrip() -> None:  # pragma: no cover - 需要外部服务
    import asyncio

    import nats

    from agh.bus import Event
    from agh.bus_nats import NatsBus

    async def run() -> None:
        nc = await nats.connect(os.environ["NATS_URL"])
        js = nc.jetstream()
        import contextlib

        with contextlib.suppress(Exception):
            await js.add_stream(name="AGH", subjects=["agh.>"])
        bus = NatsBus(js)
        seq = await bus.publish_async("jobs", Event(event_id="it-1", type="t", payload={"a": 1}))
        assert seq >= 1
        await nc.close()

    asyncio.run(run())
