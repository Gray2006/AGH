from __future__ import annotations

from pathlib import Path

from agh.audit import AuditSession
from agh.ui import build_report, render_html


def _log(tmp_path: Path) -> Path:
    path = tmp_path / "run.jsonl"
    audit = AuditSession(path, label="demo")
    good = audit.call(model="mock/good", prompt="把 [3,1,2] 升序", response="sorted([3,1,2])", tokens=42)
    bad = audit.call(model="mock/bad", prompt="把 [3,1,2] 降序", response="sorted([3,1,2])", tokens=51)
    audit.flag(bad, reason="wrong", note="要求降序，返回了升序")
    audit.note("custom.event", foo="bar")
    assert good != bad
    return path


def test_build_report_structure(tmp_path: Path) -> None:
    report = build_report(_log(tmp_path))
    assert report["summary"]["calls"] == 2
    assert report["summary"]["flags"] == 1
    assert report["summary"]["tokens"] == 93
    assert len(report["calls"]) == 2
    assert report["flags"][0]["reason"] == "wrong"
    assert any(e["type"] == "custom.event" for e in report["events"])


def test_render_html_embeds_data(tmp_path: Path) -> None:
    html = render_html(_log(tmp_path))
    assert "<!doctype html>" in html
    assert "AGH 审计报告" in html
    assert "mock/bad" in html
    assert "__DATA__" not in html


def test_render_html_escapes_closing_tags(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    audit = AuditSession(path)
    audit.call(model="m", prompt="</script><script>alert(1)</script>", response="ok")
    html = render_html(path)
    assert "</script><script>alert(1)" not in html
    assert "<\\/script>" in html


def test_report_verifies_tampered_log(tmp_path: Path) -> None:
    import pytest

    from agh.eventlog import LogTampered

    path = _log(tmp_path)
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[1] = lines[1].replace('"tokens": 42', '"tokens": 999')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(LogTampered):
        build_report(path)


def test_ui_cli_writes_file(tmp_path: Path) -> None:
    from agh.cli import main

    path = _log(tmp_path)
    out = tmp_path / "report.html"
    code = main(["ui", "--log", str(path), "--out", str(out), "--no-open"])
    assert code == 0
    assert out.exists()
    assert "AGH 审计报告" in out.read_text(encoding="utf-8")


def test_ui_from_run_default(tmp_path: Path, monkeypatch) -> None:
    import os

    from agh.cli import main
    from agh.quickstart import run_quickstart

    monkeypatch.chdir(tmp_path)
    run_quickstart(tmp_path / "agh-quickstart")
    monkeypatch.chdir(tmp_path)
    os.chdir(tmp_path)
    out = tmp_path / "r.html"
    code = main(["ui", "--from-run", "--out", str(out), "--no-open"])
    assert code == 0
    assert out.exists()


def test_ui_without_log_and_no_quickstart(tmp_path: Path, monkeypatch) -> None:
    import pytest

    from agh.cli import main

    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        main(["ui", "--out", str(tmp_path / "x.html"), "--no-open"])
