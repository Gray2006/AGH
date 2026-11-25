"""CLI 入口的冒烟测试：每个子命令至少跑通一次。

功能测试在各模块自己的文件里；这里只保证参数接线正确、不抛异常。
"""

from __future__ import annotations

import json
from pathlib import Path

from agh.audit import AuditSession
from agh.cli import main


def _log(tmp_path: Path) -> Path:
    path = tmp_path / "run.jsonl"
    audit = AuditSession(path, label="cli-test")
    cid = audit.call(model="m", prompt="p", response="r", tokens=5)
    audit.flag(cid, reason="wrong", note="n")
    return path


def test_cli_version(capsys) -> None:
    assert main(["version"]) == 0
    assert "2." in capsys.readouterr().out


def test_cli_audit_summary(tmp_path: Path, capsys) -> None:
    assert main(["audit", "summary", "--log", str(_log(tmp_path))]) == 0
    assert "calls" in capsys.readouterr().out or "ok" in capsys.readouterr().out


def test_cli_audit_verify(tmp_path: Path, capsys) -> None:
    assert main(["audit", "verify", "--log", str(_log(tmp_path))]) == 0


def test_cli_audit_export_failures(tmp_path: Path, capsys) -> None:
    out = tmp_path / "f.json"
    assert main(["audit", "export-failures", "--log", str(_log(tmp_path)), "--out", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["cases"]


def test_cli_audit_stats(tmp_path: Path, capsys) -> None:
    assert main(["audit-stats", "--log", str(_log(tmp_path))]) == 0
    assert "按模型" in capsys.readouterr().out


def test_cli_audit_timeline(tmp_path: Path, capsys) -> None:
    assert main(["audit-timeline", "--log", str(_log(tmp_path))]) == 0
    assert "llm.call" in capsys.readouterr().out


def test_cli_audit_timeline_json(tmp_path: Path, capsys) -> None:
    assert main(["audit-timeline", "--log", str(_log(tmp_path)), "--json"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert any(r["type"] == "llm.call" for r in rows)


def test_cli_audit_diff(tmp_path: Path, capsys) -> None:
    a = _log(tmp_path / "a")
    b = _log(tmp_path / "b")
    assert main(["audit-diff", "--a", str(a), "--b", str(b)]) == 0
    data = json.loads(capsys.readouterr().out)
    assert "common" in data


def test_cli_ui(tmp_path: Path, capsys) -> None:
    out = tmp_path / "r.html"
    assert main(["ui", "--log", str(_log(tmp_path)), "--out", str(out), "--no-open"]) == 0
    assert out.exists()


def test_cli_feedback(tmp_path: Path, capsys) -> None:
    out = tmp_path / "fb.md"
    assert main(["feedback", "--log", str(_log(tmp_path)), "--out", str(out)]) == 0
    assert "AGH 反馈" in out.read_text(encoding="utf-8")


def test_cli_import(tmp_path: Path, capsys) -> None:
    src = tmp_path / "src.jsonl"
    src.write_text(
        json.dumps({"model": "m", "prompt": "p", "response": "r"}), encoding="utf-8"
    )
    out = tmp_path / "o.jsonl"
    assert main(["import", "--from-jsonl", str(src), "--out", str(out)]) == 0
    assert out.exists()


def test_cli_doctor_json(capsys) -> None:
    code = main(["doctor", "--json"])
    assert code in (0, 1)
    data = json.loads(capsys.readouterr().out)
    assert "checks" in data


def test_cli_quickstart(tmp_path: Path, capsys) -> None:
    assert main(["quickstart", "--dir", str(tmp_path / "qs")]) == 0
    assert (tmp_path / "qs" / "run.jsonl").exists()
