from __future__ import annotations

import json
from pathlib import Path

from agh.quickstart import render_quickstart, run_quickstart


def test_quickstart_runs_without_keys(tmp_path: Path) -> None:
    report = run_quickstart(tmp_path / "qs")
    assert report.log_path.exists()
    assert report.failures_path.exists()
    assert report.summary["calls"] == 3
    assert report.summary["flags"] == 1


def test_quickstart_log_verifies(tmp_path: Path) -> None:
    from agh.eventlog import EventLog

    report = run_quickstart(tmp_path / "qs")
    EventLog(report.log_path).verify()  # 不抛即通过
    assert len(report.replay["head"]) == 64


def test_quickstart_exports_one_failure(tmp_path: Path) -> None:
    report = run_quickstart(tmp_path / "qs")
    data = json.loads(report.failures_path.read_text(encoding="utf-8"))
    assert len(data["cases"]) == 1
    assert data["cases"][0]["reason"] == "wrong"
    assert "降序" in data["cases"][0]["prompt"]


def test_quickstart_is_idempotent(tmp_path: Path) -> None:
    run_quickstart(tmp_path / "qs")
    second = run_quickstart(tmp_path / "qs")
    assert second.summary["calls"] == 3


def test_render_mentions_next_steps(tmp_path: Path) -> None:
    text = render_quickstart(run_quickstart(tmp_path / "qs"))
    assert "quickstart" in text
    assert "agh audit verify" in text
    assert "AuditSession" in text


def test_quickstart_writes_report(tmp_path: Path) -> None:
    report = run_quickstart(tmp_path / "qs")
    assert report.report_path is not None
    assert report.report_path.exists()
    assert "AGH 审计报告" in report.report_path.read_text(encoding="utf-8")
