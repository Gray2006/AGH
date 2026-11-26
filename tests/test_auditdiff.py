from __future__ import annotations

from pathlib import Path

from agh.audit import AuditSession
from agh.auditdiff import diff_logs


def _log(path: Path, prompts: list[str]) -> Path:
    audit = AuditSession(path)
    for prompt in prompts:
        audit.call(model="m", prompt=prompt, response="r", tokens=10)
    return path


def test_identical_logs_have_no_diff(tmp_path: Path) -> None:
    a = _log(tmp_path / "a.jsonl", ["p1", "p2"])
    b = _log(tmp_path / "b.jsonl", ["p1", "p2"])
    diff = diff_logs(a, b)
    assert diff.only_a == ()
    assert diff.only_b == ()
    assert diff.common == 2
    assert diff.stats_a["tokens"] == diff.stats_b["tokens"]


def test_added_calls_show_in_only_b(tmp_path: Path) -> None:
    a = _log(tmp_path / "a.jsonl", ["p1"])
    b = _log(tmp_path / "b.jsonl", ["p1", "p2", "p3"])
    diff = diff_logs(a, b)
    assert len(diff.only_b) == 2


def test_model_swap_is_reported_not_masked(tmp_path: Path) -> None:
    # 同样的 prompt/response 换模型跑：call_id 不含模型，集合层面看是「同一条」，
    # 但这正是 diff 该说出来的事，不能报成 0 差异。
    a = tmp_path / "a.jsonl"
    b = tmp_path / "b.jsonl"
    AuditSession(a).call(model="deepseek-chat", prompt="p", response="r", tokens=10)
    AuditSession(b).call(model="gpt-4o", prompt="p", response="r", tokens=10)

    diff = diff_logs(a, b)
    assert diff.common == 1
    assert any("deepseek-chat → gpt-4o" in note for note in diff.notes)


def test_identical_calls_produce_no_note(tmp_path: Path) -> None:
    a = _log(tmp_path / "a.jsonl", ["p1"])
    b = _log(tmp_path / "b.jsonl", ["p1"])
    assert diff_logs(a, b).notes == []


def test_token_change_is_reported_as_payload_diff(tmp_path: Path) -> None:
    a = tmp_path / "a.jsonl"
    b = tmp_path / "b.jsonl"
    AuditSession(a).call(model="m", prompt="p", response="r", tokens=100)
    AuditSession(b).call(model="m", prompt="p", response="r", tokens=999)

    diff = diff_logs(a, b)
    assert any("内容不同" in note for note in diff.notes)


def test_all_calls_replaced(tmp_path: Path) -> None:
    a = _log(tmp_path / "a.jsonl", ["x1", "x2"])
    b = _log(tmp_path / "b.jsonl", ["y1"])
    diff = diff_logs(a, b)
    assert len(diff.only_a) == 2
    assert len(diff.only_b) == 1
    assert any("全部消失" in note for note in diff.notes)


def test_diff_cli(tmp_path: Path) -> None:
    from agh.cli import main

    a = _log(tmp_path / "a.jsonl", ["p1"])
    b = _log(tmp_path / "b.jsonl", ["p1", "p2"])
    assert main(["audit-diff", "--a", str(a), "--b", str(b)]) == 0


def test_diff_cli_missing_file(tmp_path: Path) -> None:
    import pytest

    from agh.cli import main

    with pytest.raises(SystemExit):
        main(["audit-diff", "--a", "nope.jsonl", "--b", "nope2.jsonl"])
