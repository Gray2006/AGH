"""校准回归：验证器改动不能悄悄降低与人工分级的一致性。

数据来自人工分级标注（19 题，0/0.5/1）。阈值留了余量：
当前 ECE 0.009，门限 0.05；二值 kappa 当前 1.0，门限 0.9。
"""

from __future__ import annotations

import json
from pathlib import Path

from agh.calibration import cohen_kappa, ece
from agh.contracts import GestaltReconstruction, Skeleton
from agh.verifier import StructuralVerifier

FIXTURE = Path(__file__).parent / "fixtures" / "calibration.json"
MAX_ECE = 0.05
MIN_KAPPA = 0.9


def _scores() -> tuple[list[float], list[float]]:
    items = json.loads(FIXTURE.read_text(encoding="utf-8"))
    verifier = StructuralVerifier()
    machine: list[float] = []
    human: list[float] = []
    for item in items:
        skeleton = Skeleton.model_validate(item["skeleton"])
        recon = GestaltReconstruction.model_validate(item["reconstruction"])
        machine.append(verifier.score(recon, skeleton))
        human.append(float(item["label"]))
    return machine, human


def test_calibration_ece_within_budget() -> None:
    machine, human = _scores()
    assert ece(machine, human) <= MAX_ECE


def test_calibration_binary_agreement() -> None:
    machine, human = _scores()
    kappa = cohen_kappa([m >= 0.99 for m in machine], [h >= 0.99 for h in human])
    assert kappa >= MIN_KAPPA


def test_fixture_is_balanced() -> None:
    _, human = _scores()
    positives = sum(1 for h in human if h == 1.0)
    partials = sum(1 for h in human if h == 0.5)
    assert positives >= 5 and partials >= 5
