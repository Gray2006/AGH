from __future__ import annotations

import json
from pathlib import Path

import pytest

from agh.eventlog import (
    EventLog,
    L1Replay,
    LogEntry,
    LogTampered,
    l2_statistical_equivalence,
    state_digest,
)


def reducer(state: dict, entry: LogEntry) -> dict:
    s = dict(state)
    s["count"] = s.get("count", 0) + 1
    s["last"] = entry.payload.get("v", 0)
    return s


def test_append_and_verify(tmp_path: Path) -> None:
    log = EventLog(tmp_path / "e.jsonl", clock=lambda: 1)
    log.append("a", {"v": 1})
    log.append("b", {"v": 2})
    log.verify()
    reloaded = EventLog(tmp_path / "e.jsonl", clock=lambda: 1)
    reloaded.verify()
    assert [e.seq for e in reloaded.entries] == [1, 2]


def test_tampered_log_detected(tmp_path: Path) -> None:
    path = tmp_path / "e.jsonl"
    log = EventLog(path, clock=lambda: 1)
    log.append("a", {"v": 1})
    log.append("b", {"v": 2})
    lines = path.read_text(encoding="utf-8").splitlines()
    raw = json.loads(lines[0])
    raw["payload"]["v"] = 999
    lines[0] = json.dumps(raw, ensure_ascii=False)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tampered = EventLog(path, clock=lambda: 1)
    with pytest.raises(LogTampered):
        tampered.verify()


def test_l1_replay_bit_exact(tmp_path: Path) -> None:
    log = EventLog(tmp_path / "e.jsonl", clock=lambda: 1)
    state = {"count": 0}
    for v in (1, 2, 3):
        probe = LogEntry(seq=0, ts=0, type="x", payload={"v": v}, prev_hash="", hash="")
        state = reducer(state, probe)
        log.append("x", {"v": v, "state_digest": state_digest(state)})
    report = L1Replay(log, reducer, {"count": 0}).run()
    assert report.bit_exact
    assert report.steps == 3


def test_l1_replay_detects_digest_drift(tmp_path: Path) -> None:
    log = EventLog(tmp_path / "e.jsonl", clock=lambda: 1)
    state = {"count": 0}
    for v in (1, 2):
        probe = LogEntry(seq=0, ts=0, type="x", payload={"v": v}, prev_hash="", hash="")
        state = reducer(state, probe)
        digest = state_digest(state)
        if v == 2:
            digest = "f" * 64  # 记录下来的状态与重放不一致
        log.append("x", {"v": v, "state_digest": digest})
    report = L1Replay(log, reducer, {"count": 0}).run()
    assert not report.bit_exact
    assert report.mismatches == [2]


def test_l2_statistical_equivalence() -> None:
    a = [0.8, 0.81, 0.79, 0.8]
    b = [0.82, 0.80, 0.81, 0.80]
    report = l2_statistical_equivalence(a, b, tolerance=0.05)
    assert report["within_tolerance"]
    far = l2_statistical_equivalence(a, [0.1, 0.2], tolerance=0.05)
    assert not far["within_tolerance"]


def test_broken_line_raises_logtampered(tmp_path: Path) -> None:
    import pytest

    from agh.eventlog import EventLog, LogTampered

    path = tmp_path / "broken.jsonl"
    path.write_text('{"type":"a"}\nnot-json\n', encoding="utf-8")
    with pytest.raises(LogTampered, match="损坏"):
        EventLog(path)


def test_unicode_line_separators_survive(tmp_path: Path) -> None:
    """内容里的 U+2028 不能把一条记录切成两半（splitlines 会这么做）。"""
    from agh.eventlog import EventLog

    path = tmp_path / "log.jsonl"
    log = EventLog(path)
    log.append("t", {"text": "前\u2028后"})
    log.append("t", {"text": "垂直制表\u000b结束"})

    fresh = EventLog(path)
    fresh.verify()
    assert len(fresh.entries) == 2
    assert fresh.entries[0].payload["text"] == "前\u2028后"


def test_non_utf8_log_raises_logunreadable(tmp_path: Path) -> None:
    """用户把别的工具的 GBK 输出当日志传进来，不能甩 UnicodeDecodeError。"""
    import pytest

    from agh.eventlog import EventLog, LogTampered, LogUnreadable

    path = tmp_path / "gbk.jsonl"
    path.write_bytes('{"seq": 1, "type": "中文"}'.encode("gbk") + b"\n")

    with pytest.raises(LogUnreadable, match="UTF-8"):
        EventLog(path)
    # 继承关系：既有 except LogTampered 的调用点继续可用
    assert issubclass(LogUnreadable, LogTampered)


def test_bom_in_log_is_transparent(tmp_path: Path) -> None:
    """记事本另存为加的 BOM 是编码标记，不是内容：链仍然应该校验通过。"""
    from agh.eventlog import EventLog

    path = tmp_path / "log.jsonl"
    log = EventLog(path)
    log.append("t", {"text": "内容"})
    expected_head = log.head()

    raw = path.read_bytes()
    path.write_bytes(b"\xef\xbb\xbf" + raw)

    fresh = EventLog(path)
    fresh.verify()
    assert fresh.head() == expected_head


def test_cli_reports_unreadable_log_cleanly(tmp_path: Path) -> None:
    from agh.cli import main

    path = tmp_path / "gbk.jsonl"
    path.write_bytes('{"seq": 1, "type": "中文"}'.encode("gbk") + b"\n")
    assert main(["audit", "summary", "--log", str(path)]) == 2
