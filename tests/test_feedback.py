from __future__ import annotations

from pathlib import Path

from agh.audit import AuditSession
from agh.feedback import build_feedback


def _log(tmp_path: Path) -> Path:
    path = tmp_path / "run.jsonl"
    audit = AuditSession(path)
    cid = audit.call(model="deepseek-chat", prompt="机密输入内容", response="机密输出内容", tokens=10)
    audit.flag(cid, reason="wrong", note="边界没处理")
    return path


def test_feedback_is_redacted_by_default(tmp_path: Path) -> None:
    text = build_feedback(_log(tmp_path))
    assert "AGH 反馈" in text
    assert "wrong" in text
    assert "机密输入内容" not in text
    assert "机密输出内容" not in text
    assert "prompt_sha256" in text


def test_feedback_can_include_payload(tmp_path: Path) -> None:
    text = build_feedback(_log(tmp_path), with_payload=True)
    assert "机密输入内容" in text
    assert "机密输出内容" in text


def test_feedback_has_issue_template(tmp_path: Path) -> None:
    text = build_feedback(_log(tmp_path))
    assert "复现步骤" in text
    assert "期望行为" in text


def test_feedback_without_flags(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    AuditSession(path).call(model="m", prompt="p", response="r")
    text = build_feedback(path)
    assert "没有标记过的调用" in text


def test_note_is_sanitized(tmp_path: Path) -> None:
    """note 是自由文本，控制字符必须清掉、长度要收。"""
    path = tmp_path / "run.jsonl"
    audit = AuditSession(path)
    cid = audit.call(model="m", prompt="p", response="r")
    audit.flag(cid, reason="wrong", note="带\x00空字节" + "长" * 800)
    text = build_feedback(path)
    assert "\x00" not in text
    assert "长" * 200 not in text


def test_fence_adapts_to_content(tmp_path: Path) -> None:
    """内容里有 ``` 时，围栏要更长，不能把 markdown 撑破。"""
    path = tmp_path / "run.jsonl"
    audit = AuditSession(path)
    cid = audit.call(model="m", prompt="```\n代码\n```", response="ok")
    audit.flag(cid, reason="wrong")
    text = build_feedback(path, with_payload=True)
    assert "````" in text
