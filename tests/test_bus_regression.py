"""回归测试：批次大于去重窗口时仍要返回正确序号（旧实现会 KeyError）。"""

from __future__ import annotations

from agh.bus import Event, InProcBus


def ev(eid: str, n: int = 1) -> Event:
    return Event(event_id=eid, type="job", payload={"n": n})


def test_batch_larger_than_window_returns_all_seqs() -> None:
    bus = InProcBus(dedup_window=1)
    seqs = bus.publish_batch("jobs", [ev("a"), ev("b"), ev("c")])
    assert seqs == [1, 2, 3]
    assert bus.last_seq("jobs") == 3


def test_batch_larger_than_window_keeps_newest_in_window() -> None:
    bus = InProcBus(dedup_window=2)
    bus.publish_batch("jobs", [ev("a"), ev("b"), ev("c")])
    assert bus.publish("jobs", ev("c")) == 3  # 最新一条仍在窗口内
    assert bus.publish("jobs", ev("a")) == 4  # 旧的已被挤出窗口，重新入库
