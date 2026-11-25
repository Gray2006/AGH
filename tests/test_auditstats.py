from __future__ import annotations

from pathlib import Path

from agh.audit import AuditSession
from agh.auditstats import compute_stats, render


def _log(tmp_path: Path) -> Path:
    path = tmp_path / "run.jsonl"
    audit = AuditSession(path)
    audit.call(model="a", prompt="p1", response="r1", tokens=10)
    audit.call(model="a", prompt="p2", response="r2", tokens=20)
    cid = audit.call(model="b", prompt="p3", response="r3", tokens=5)
    audit.flag(cid, reason="wrong")
    return path


def test_stats_aggregate_by_model(tmp_path: Path) -> None:
    stats = compute_stats(_log(tmp_path))
    assert stats.total_calls == 3
    assert stats.total_tokens == 35
    assert stats.flags == 1
    assert stats.by_model["a"] == {"calls": 2, "tokens": 30}
    assert stats.by_model["b"] == {"calls": 1, "tokens": 5}


def test_stats_has_time_range(tmp_path: Path) -> None:
    stats = compute_stats(_log(tmp_path))
    assert stats.first_ts and stats.last_ts
    assert stats.first_ts <= stats.last_ts


def test_stats_render_contains_sections(tmp_path: Path) -> None:
    text = render(compute_stats(_log(tmp_path)))
    assert "按模型" in text
    assert "tokens 35" in text


def test_stats_cli_json(tmp_path: Path) -> None:
    from agh.cli import main

    assert main(["audit-stats", "--log", str(_log(tmp_path)), "--json"]) == 0


def test_stats_missing_log(tmp_path: Path) -> None:
    import pytest

    from agh.cli import main

    with pytest.raises(SystemExit):
        main(["audit-stats", "--log", "nope.jsonl"])
