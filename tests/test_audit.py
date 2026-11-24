from __future__ import annotations

import json
from pathlib import Path

import pytest

from agh.audit import AuditSession, export_failures
from agh.eventlog import LogTampered


def _session(path: Path, **kwargs) -> AuditSession:
    return AuditSession(path, **kwargs)


def test_call_and_flag_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    with _session(path) as audit:
        cid = audit.call(model="deepseek-chat", prompt="写个快排", response="def qs(...)", tokens=120)
        audit.flag(cid, reason="wrong", note="边界没处理")

    summary = audit.summary()
    assert summary["calls"] == 1
    assert summary["flags"] == 1
    assert summary["tokens"] == 120
    assert audit.verify() is True


def test_verify_detects_tamper(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    audit = _session(path)
    audit.call(model="m", prompt="p", response="r", tokens=1)
    audit.verify()

    lines = path.read_text(encoding="utf-8").splitlines()
    lines[1] = lines[1].replace('"tokens": 1', '"tokens": 999')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(LogTampered):
        audit.verify()


def test_replay_reports_types(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    with _session(path) as audit:
        audit.call(model="m", prompt="p", response="r")
    report = audit.replay()
    assert report["types"]["session.start"] == 1
    assert report["types"]["llm.call"] == 1
    assert len(report["head"]) == 64


def test_store_payload_false_keeps_only_hashes(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    audit = _session(path, store_payload=False)
    audit.call(model="m", prompt="机密输入", response="机密输出")
    text = path.read_text(encoding="utf-8")
    assert "机密输入" not in text
    assert "prompt_sha256" in text


def test_export_redacted_drops_payload(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    audit = _session(path)
    audit.call(model="m", prompt="原文", response="结果")
    out = audit.export(tmp_path / "bundle.json", redact=True)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["redacted"] is True
    assert all("prompt" not in e["payload"] for e in data["events"])


def test_export_failures_only_flagged(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    audit = _session(path)
    good = audit.call(model="m", prompt="p1", response="r1")
    bad = audit.call(model="m", prompt="p2", response="r2")
    audit.flag(bad, reason="wrong")

    out = tmp_path / "failures.json"
    n = export_failures(path, out)
    assert n == 1
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["cases"][0]["call_id"] == bad
    assert data["cases"][0]["reason"] == "wrong"
    assert data["cases"][0]["prompt"] == "p2"
    assert good != bad


def test_export_failures_without_payload(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    audit = _session(path, store_payload=False)
    cid = audit.call(model="m", prompt="p", response="r")
    audit.flag(cid, reason="wrong")
    out = tmp_path / "failures.json"
    assert export_failures(path, out) == 1
    case = json.loads(out.read_text(encoding="utf-8"))["cases"][0]
    assert "prompt" not in case
    assert len(case["prompt_sha256"]) == 64


def test_identical_calls_get_distinct_ids(tmp_path: Path) -> None:
    """内容完全相同的两次调用必须拿到不同 call_id，否则 flag 会串到另一条。"""
    audit = _session(tmp_path / "run.jsonl")
    first = audit.call(model="m", prompt="同一个输入", response="同一个输出")
    second = audit.call(model="m", prompt="同一个输入", response="同一个输出")
    assert first != second
    audit.flag(second, reason="wrong")
    text = (tmp_path / "run.jsonl").read_text(encoding="utf-8")
    assert text.count('"llm.flag"') == 1
