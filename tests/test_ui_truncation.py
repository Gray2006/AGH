"""大日志自动截断：1 万条能生成 8MB HTML，浏览器打不开。"""

from __future__ import annotations

import json
from pathlib import Path

from agh.audit import AuditSession
from agh.cli import DEFAULT_UI_MAX_CALLS, main


def _big_log(tmp_path: Path, n: int = 60) -> Path:
    path = tmp_path / "big.jsonl"
    audit = AuditSession(path)
    for i in range(n):
        audit.call(model="m", prompt=f"p{i}", response="r" * 50, tokens=1)
    return path


def test_small_log_is_not_truncated(tmp_path: Path, capsys) -> None:
    log = _big_log(tmp_path, 5)
    out = tmp_path / "r.html"
    assert main(["ui", "--log", str(log), "--out", str(out), "--no-open"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert "note" not in data


def test_large_log_truncates_with_note(tmp_path: Path, capsys, monkeypatch) -> None:
    import agh.cli as cli

    monkeypatch.setattr(cli, "DEFAULT_UI_MAX_CALLS", 10)
    log = _big_log(tmp_path, 30)
    out = tmp_path / "r.html"
    assert main(["ui", "--log", str(log), "--out", str(out), "--no-open"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert "note" in data
    assert "截断" in data["note"]


def test_explicit_max_calls_wins(tmp_path: Path, capsys, monkeypatch) -> None:
    import agh.cli as cli

    monkeypatch.setattr(cli, "DEFAULT_UI_MAX_CALLS", 10)
    log = _big_log(tmp_path, 30)
    out = tmp_path / "r.html"
    assert main(["ui", "--log", str(log), "--out", str(out), "--max-calls", "0", "--no-open"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert "note" not in data


def test_default_constant_is_sane() -> None:
    assert DEFAULT_UI_MAX_CALLS >= 1000
