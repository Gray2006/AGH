from __future__ import annotations

from pathlib import Path

from agh.redteam import report, run_attacks


def test_all_attacks_defended(frozen_src: Path) -> None:
    payload = report(run_attacks(frozen_src))
    assert payload["all_defended"], payload["results"]
    assert payload["total"] >= 7


def test_log_truncation_needs_anchor() -> None:
    import tempfile
    from pathlib import Path as P

    from agh.eventlog import EventLog, LogTampered

    with tempfile.TemporaryDirectory() as tmp:
        path = P(tmp) / "e.jsonl"
        log = EventLog(path)
        for i in range(3):
            log.append("t", {"i": i})
        head, size = log.head(), log.size()
        lines = path.read_text(encoding="utf-8").splitlines()
        path.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
        EventLog(path).verify()  # 本地链看不出来
        try:
            EventLog(path).verify_against(head, size)
        except LogTampered:
            pass
        else:
            raise AssertionError("锚点比对应发现截断")
