from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from agh.cli import main
from agh.sdk import AghClient


@pytest.fixture()
def client(frozen_root: Path, tmp_path: Path) -> AghClient:
    return AghClient(frozen_root=frozen_root, run_dir=tmp_path / "run")


def test_sdk_run_verify_replay(client: AghClient) -> None:
    report = client.run()
    assert report.winner == "child-faithful"
    assert client.verify_log()
    replay = client.replay()
    assert replay.bit_exact


def test_sdk_experiment_and_ablation(client: AghClient) -> None:
    experiment = client.experiment(seeds=4, resamples=100)
    assert experiment.seeds == 4
    ablation = client.ablation(seeds=3, resamples=100)
    assert ablation.seeds == 3


def test_cli_run_and_verify(frozen_root: Path, tmp_path: Path) -> None:
    root = tmp_path / "repo"
    (root / "config").mkdir(parents=True)
    shutil.copytree(frozen_root, root / "config" / "frozen")
    run_dir = tmp_path / "cli-run"
    code = main(["run", "--root", str(root), "--out", str(run_dir)])
    assert code == 0
    assert main(["verify", "--run-dir", str(run_dir)]) == 0
    assert main(["replay", "--run-dir", str(run_dir)]) == 0


def test_cli_version(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["version"]) == 0
    assert capsys.readouterr().out.strip()
