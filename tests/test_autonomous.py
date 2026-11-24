from __future__ import annotations

from pathlib import Path

from agh.autonomous import AutonomousConfig, calibration_ok, run_autonomous


def test_calibration_gate_passes() -> None:
    ok, detail = calibration_ok()
    assert ok, detail


def test_run_autonomous_no_write_back(frozen_src: Path, tmp_path: Path) -> None:
    report = run_autonomous(
        frozen_src,
        AutonomousConfig(rounds=2, generations=1, population=2, benchmarks=3, patience=2, write_back=False),
    )
    assert report.rounds_run >= 1
    assert report.curve
    assert report.written_back is False


def test_write_back_path(frozen_src: Path) -> None:
    import json

    report = run_autonomous(
        frozen_src,
        AutonomousConfig(rounds=1, generations=1, population=2, benchmarks=3, write_back=True),
    )
    assert report.written_back or report.rolled_back
    data = json.loads((frozen_src / "thresholds.json").read_text(encoding="utf-8"))
    assert abs(sum(data["arena"]["weights"].values()) - 1.0) < 1e-6
