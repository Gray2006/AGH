from __future__ import annotations

from pathlib import Path

from agh.anomaly import EMPTY_SHA256, Thresholds, detect
from agh.audit import AuditSession
from agh.ui import build_report, render_html


def _call(call_id: str, tokens: int = 10, prompt_sha: str = "p", resp_sha: str = "r",
          model: str = "m") -> dict:
    return {
        "call_id": call_id,
        "model": model,
        "category": "",
        "tokens": tokens,
        "prompt_sha256": prompt_sha,
        "response_sha256": resp_sha,
    }


def test_token_spike_needs_enough_samples() -> None:
    """样本不足时不报，避免小日志上瞎报警。"""
    calls = [_call(f"c{i}", tokens=10) for i in range(5)]
    calls.append(_call("big", tokens=100_000))
    assert detect(calls, thresholds=Thresholds(min_samples=20)) == []


def test_token_spike_fires_above_threshold() -> None:
    calls = [_call(f"c{i}", tokens=100) for i in range(40)]
    calls.append(_call("big", tokens=50_000))
    found = detect(calls, thresholds=Thresholds(min_samples=20, spike_factor=3.0))
    assert [f.rule for f in found] == ["token_spike"]
    assert found[0].call_id == "big"


def test_duplicate_prompt_reports_once_per_group() -> None:
    """一组重复输入只报一条，否则一轮对话几十步会全部标红。"""
    calls = [
        _call(f"c{i}", prompt_sha="same", resp_sha=f"out{i}")
        for i in range(25)
    ]
    found = detect(calls, thresholds=Thresholds(duplicate_min=20, duplicate_outputs=5))
    dup = [f for f in found if f.rule == "duplicate_prompt"]
    assert len(dup) == 1
    assert dup[0].group is True
    assert len(dup[0].all_ids()) == 25


def test_duplicate_prompt_ignores_stable_output() -> None:
    """同一输入但输出完全一致，不算异常。"""
    calls = [_call(f"c{i}", prompt_sha="same", resp_sha="same_out") for i in range(30)]
    found = detect(calls, thresholds=Thresholds(duplicate_min=20, duplicate_outputs=5))
    assert not [f for f in found if f.rule == "duplicate_prompt"]


def test_empty_response_detected() -> None:
    found = detect([_call("c1", resp_sha=EMPTY_SHA256)])
    assert [f.rule for f in found] == ["empty_response"]


def test_zero_tokens_detected() -> None:
    found = detect([_call("c1", tokens=0, resp_sha="has_output")])
    assert [f.rule for f in found] == ["zero_tokens"]


def test_report_includes_anomalies(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    audit = AuditSession(path)
    audit.call(model="m", prompt="p", response="", tokens=0)

    report = build_report(path)
    assert report["summary"]["anomalies"] >= 1
    rules = {a["rule"] for a in report["anomalies"]}
    assert "empty_response" in rules
    assert report["anomalies"][0]["call_ids"]


def test_report_can_disable_anomalies(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    audit = AuditSession(path)
    audit.call(model="m", prompt="p", response="", tokens=0)

    report = build_report(path, anomalies=False)
    assert report["anomalies"] == []
    assert report["summary"]["anomalies"] == 0


def test_ui_cli_no_anomaly_flag(tmp_path: Path) -> None:
    from agh.cli import main

    path = tmp_path / "run.jsonl"
    audit = AuditSession(path)
    audit.call(model="m", prompt="p", response="", tokens=0)

    out = tmp_path / "on.html"
    main(["ui", "--log", str(path), "--out", str(out), "--no-open"])
    assert "自动检查" in out.read_text(encoding="utf-8")

    out2 = tmp_path / "off.html"
    main(["ui", "--log", str(path), "--out", str(out2), "--no-open", "--no-anomaly"])
    assert '"anomalies": []' in out2.read_text(encoding="utf-8")


def test_english_labels_for_anomalies(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    audit = AuditSession(path)
    audit.call(model="m", prompt="p", response="", tokens=0)
    html = render_html(path, lang="en")
    assert "Automatic checks" in html
    assert "Auto-flagged" in html
