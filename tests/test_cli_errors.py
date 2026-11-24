from __future__ import annotations

from pathlib import Path

import pytest

from agh.cli import main


def test_missing_log_is_an_error_not_ok(capsys) -> None:
    """最严重的自欺：校验一个不存在的文件却返回 ok: true。"""
    with pytest.raises(SystemExit) as exc:
        main(["audit", "verify", "--log", "no-such-file.jsonl"])
    assert "找不到" in str(exc.value)


def test_audit_summary_missing_log(capsys) -> None:
    with pytest.raises(SystemExit):
        main(["audit", "summary", "--log", "no-such-file.jsonl"])


def test_export_failures_missing_log(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        main(["audit", "export-failures", "--log", "no-such-file.jsonl", "--out", str(tmp_path / "x")])


def test_ui_missing_log(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        main(["ui", "--log", "no-such-file.jsonl", "--out", str(tmp_path / "x.html"), "--no-open"])


def test_feedback_missing_log(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        main(["feedback", "--log", "no-such-file.jsonl", "--out", str(tmp_path / "f.md")])


def test_import_missing_source(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        main(["import", "--from-jsonl", "no-such-file.jsonl", "--out", str(tmp_path / "o.jsonl")])


def test_ui_rejects_log_and_from_run_together(tmp_path: Path) -> None:
    log = tmp_path / "run.jsonl"
    log.write_text("", encoding="utf-8")
    with pytest.raises(SystemExit):
        main(
            [
                "ui",
                "--log",
                str(log),
                "--from-run",
                "--out",
                str(tmp_path / "x.html"),
                "--no-open",
            ]
        )


def test_existing_empty_log_still_verifies(tmp_path: Path) -> None:
    """空日志是合法的（新会话），不能因为空就报错。"""
    log = tmp_path / "empty.jsonl"
    log.write_text("", encoding="utf-8")
    assert main(["audit", "verify", "--log", str(log)]) == 0
