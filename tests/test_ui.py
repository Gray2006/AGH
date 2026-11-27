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


def test_report_js_strings_keep_escapes(tmp_path: Path) -> None:
    """模板是普通字符串时，JS 里的 "\\n" 会变成真换行 → 整段脚本语法错误 → 白页。

    v3.1.0 加 CSV 下载时就踩了这个：`lines.join("\\n")` 变成跨行字符串，
    报告从此渲染不出来，而只做字符串断言的测试全绿。
    """
    html = render_html(_log(tmp_path))
    script = html.split("<script>", 1)[1]

    # 必须保留字面反斜杠 + n
    assert 'lines.join("\\n")' in script
    # 真换行出现在 join 的引号之间 = JS 未闭合字符串
    assert 'lines.join("\n")' not in script
    # BOM 同理：必须是转义序列，不是裸字符
    assert '"\\ufeff"' in script
    assert '"\ufeff"' not in script


def test_render_html_escapes_closing_tags(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    audit = AuditSession(path)
    audit.call(model="m", prompt="</script><script>alert(1)</script>", response="ok")
    html = render_html(path)
    assert "</script><script>alert(1)" not in html
    assert "<\\/script>" in html


def test_valid_log_reports_verified(tmp_path: Path) -> None:
    data = build_report(_log(tmp_path))
    assert data["verified"] is True
    assert data["verify_error"] == ""


def test_tampered_log_renders_unverified_instead_of_crashing(tmp_path: Path) -> None:
    path = _log(tmp_path)
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[1] = lines[1].replace('"tokens": 42', '"tokens": 999')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    data = build_report(path)
    assert data["verified"] is False
    assert "seq=" in data["verify_error"]
    # 篡改只影响校验结论，历史调用仍应尽量保住
    assert data["summary"]["calls"] == 2

    html = render_html(path)
    assert '"verified": false' in html


def test_unparsable_log_still_renders(tmp_path: Path) -> None:
    path = _log(tmp_path)
    text = path.read_text(encoding="utf-8")
    path.write_text("{not json at all\n" + text, encoding="utf-8")

    data = build_report(path)
    assert data["verified"] is False
    # 坏行被跳过，好行保留
    assert data["summary"]["calls"] == 2
    assert '"verified": false' in render_html(path)


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


def test_ui_has_filters(tmp_path: Path) -> None:
    html = render_html(_log(tmp_path))
    assert 'id="f-model"' in html
    assert 'id="f-flagged"' in html
    assert 'id="f-search"' in html
    assert "renderCalls" in html
    assert "__DATA__" not in html


def _big_log(tmp_path: Path, n: int) -> Path:
    path = tmp_path / "big.jsonl"
    audit = AuditSession(path)
    last = ""
    for i in range(n):
        last = audit.call(model="m", prompt=f"p{i}", response=f"r{i}", tokens=1)
    audit.flag(last, reason="wrong")
    return path


def test_large_log_is_truncated(tmp_path: Path) -> None:
    from agh.ui import build_report

    report = build_report(_big_log(tmp_path, 30), max_calls=10)
    assert report["truncated"] is True
    assert report["total_calls"] == 30
    assert len(report["calls"]) == 10


def test_truncation_keeps_flagged_calls(tmp_path: Path) -> None:
    from agh.ui import build_report

    report = build_report(_big_log(tmp_path, 30), max_calls=5)
    flagged_id = report["flags"][0]["call_id"]
    assert any(c["call_id"] == flagged_id for c in report["calls"])


def test_no_truncation_under_limit(tmp_path: Path) -> None:
    from agh.ui import build_report

    report = build_report(_big_log(tmp_path, 5), max_calls=10)
    assert report["truncated"] is False
    assert len(report["calls"]) == 5


def test_report_has_csv_download(tmp_path: Path) -> None:
    """报告里要有纯前端的 CSV 下载入口（不请求后端）。"""
    html = render_html(_log(tmp_path))
    assert "下载 CSV" in html
    assert "agh-calls.csv" in html
    assert "Blob(" in html


def test_report_defaults_to_chinese(tmp_path: Path) -> None:
    html = render_html(_log(tmp_path))
    assert "AGH 审计报告" in html
    assert "哈希链校验通过" in html
    assert "输入哈希" in html


def test_report_english_labels(tmp_path: Path) -> None:
    html = render_html(_log(tmp_path), lang="en")
    for probe in (
        "AGH Audit Report",
        "Hash chain verified",
        "Model calls",
        "Download CSV",
        "input hash",
        "output hash",
        "Show raw",
    ):
        assert probe in html, probe
    # 中文 UI 文案不该残留
    assert "哈希链校验通过" not in html
    assert "下载 CSV" not in html


def test_report_has_no_unresolved_placeholders(tmp_path: Path) -> None:
    """两种语言都不能留下 @@L:xxx@@ 占位符。"""
    import re

    for lang in ("zh", "en"):
        html = render_html(_log(tmp_path), lang=lang)
        assert not re.search(r"@@L:[a-z_]+@@", html), lang


def test_ui_cli_accepts_lang(tmp_path: Path) -> None:
    from agh.cli import main

    out = tmp_path / "r.html"
    code = main(["ui", "--log", str(_log(tmp_path)), "--out", str(out), "--lang", "en", "--no-open"])
    assert code == 0
    assert "AGH Audit Report" in out.read_text(encoding="utf-8")
