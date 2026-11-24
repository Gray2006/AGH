from __future__ import annotations

from pathlib import Path

from agh.code_arena import OVERFIT_WARN, run_code_arena
from agh.codetasks import TASKS

ROOT = Path(__file__).resolve().parents[1]


def _good(_task):
    return TASKS["dedupe"].reference


def _bad(_task):
    return "def dedupe(items):\n    return items\n"


def test_arena_picks_by_visible_and_reports_hidden(tmp_path: Path) -> None:
    report = run_code_arena(
        TASKS["dedupe"],
        [("child-good", _good), ("child-bad", _bad)],
        run_dir=tmp_path,
        frozen_root=ROOT / "config" / "frozen",
    )
    assert report.winner == "child-good"
    assert report.admitted == 2
    assert report.log_ok is True
    by_id = {c.child_id: c for c in report.candidates}
    assert by_id["child-good"].hidden == 1.0
    assert by_id["child-bad"].hidden < 1.0


def test_arena_survives_failing_solver(tmp_path: Path) -> None:
    def broken(_task):
        raise RuntimeError("HTTP 402")

    report = run_code_arena(
        TASKS["dedupe"],
        [("child-ok", _good), ("child-dead", broken)],
        run_dir=tmp_path,
        frozen_root=ROOT / "config" / "frozen",
    )
    assert report.winner == "child-ok"
    assert report.log_ok is True


def test_arena_warns_on_overfit(tmp_path: Path) -> None:
    """一个只会背 visible 的候选：visible 高、hidden 低，仲裁仍按 visible 选它，但必须报警。"""
    task = TASKS["dedupe"]
    vis = task.spec.visible[0]
    cheat = (
        "def dedupe(items):\n"
        f"    if items == {vis.args[0]!r}:\n"
        f"        return {vis.expected!r}\n"
        "    return []\n"
    )

    def cheater(_task):
        return cheat

    report = run_code_arena(
        task, [("child-cheat", cheater)], run_dir=tmp_path, frozen_root=ROOT / "config" / "frozen"
    )
    assert report.winner == "child-cheat"
    assert any("visible-hidden" in note for note in report.notes)
    assert report.candidates[0].overfit_gap > OVERFIT_WARN


def test_arena_log_is_replayable(tmp_path: Path) -> None:
    from agh.eventlog import EventLog

    report = run_code_arena(
        TASKS["dedupe"], [("child-good", _good)], run_dir=tmp_path, frozen_root=ROOT / "config" / "frozen"
    )
    log = EventLog(tmp_path / "events.jsonl")
    log.verify()  # 不抛即通过
    assert log.head() == report.log_head
    types = [e.type for e in log.entries]
    assert "contract.issued" in types and "arbitration" in types
