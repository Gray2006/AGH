from __future__ import annotations

from pathlib import Path

from agh.pipeline import INITIAL_STATE, run_m0


def test_m0_end_to_end_with_dissent_escalates(tmp_path: Path, frozen_root: Path) -> None:
    report = run_m0(
        frozen_root=frozen_root,
        run_dir=tmp_path / "run",
        include_dissent=True,
        forge_attempt=True,
    )
    assert report.winner == "child-faithful"
    assert report.contested
    assert "child-dissent" in report.dissents
    assert report.l1_bit_exact
    assert report.ledger_violations == 0
    assert not report.diversity["sufficient"] or report.diversity["clusters"] >= 2
    # 伪造提交必须被拒
    assert any("child-forged" in r for r in report.rejected)
    # 存在合格异议且无人批准 → 停在 VERIFIED
    assert report.governance_state == "VERIFIED"
    assert any("T2" in n or "人工" in n for n in report.notes)
    assert (tmp_path / "run" / "report.json").exists()
    assert (tmp_path / "run" / "events.jsonl").exists()


def test_m0_clean_run_releases(tmp_path: Path, frozen_root: Path) -> None:
    report = run_m0(
        frozen_root=frozen_root,
        run_dir=tmp_path / "run",
        include_dissent=False,
    )
    assert report.winner == "child-faithful"
    assert not report.contested
    assert report.governance_state == "RELEASED"
    assert report.l1_bit_exact


def test_m0_human_approved_releases(tmp_path: Path, frozen_root: Path) -> None:
    report = run_m0(
        frozen_root=frozen_root,
        run_dir=tmp_path / "run",
        include_dissent=True,
        human_approved=True,
    )
    assert report.contested
    assert report.governance_state == "RELEASED"


def test_shallow_candidate_rejected_by_hard_filter(tmp_path: Path, frozen_root: Path) -> None:
    report = run_m0(
        frozen_root=frozen_root,
        run_dir=tmp_path / "run",
        include_dissent=False,
    )
    assert any("child-shallow" in r for r in report.rejected)


def test_initial_state_is_plain_data() -> None:
    assert INITIAL_STATE["winner"] is None
    assert INITIAL_STATE["scores"] == {}
