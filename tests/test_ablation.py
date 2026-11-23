from __future__ import annotations

import json
from pathlib import Path

import pytest

from agh.ablation import ABLATIONS, run_ablation
from agh.arena import ArenaConfig
from agh.experiment import Arm
from agh.llm import RuleChild
from agh.pipeline import (
    PARENT_SIG,
    dissent_child,
    faithful_child,
    m0_skeleton,
    shallow_child,
)


@pytest.fixture()
def cfg(frozen_src: Path) -> ArenaConfig:
    return ArenaConfig.from_frozen(frozen_src)


def arms() -> list[Arm]:
    return [
        Arm("faithful", RuleChild("faithful", faithful_child)),
        Arm("dissent", RuleChild("dissent", dissent_child)),
        Arm("shallow", RuleChild("shallow", shallow_child)),
    ]


def test_ablation_suite_has_eight_variants() -> None:
    assert len(ABLATIONS) == 8
    names = {a.name for a in ABLATIONS}
    assert "no_vertical" in names and "no_arena" in names


def test_ablation_runs_and_reports(cfg: ArenaConfig) -> None:
    report = run_ablation(
        arms(),
        m0_skeleton(),
        cfg,
        parent_features=PARENT_SIG.features,
        seeds=range(6),
        resamples=200,
    )
    data = report.as_dict()
    assert data["seeds"] == 6
    assert len(data["rows"]) == 8
    for row in data["rows"]:
        assert row["delta"]["lo"] <= row["delta"]["mean"] <= row["delta"]["hi"]
        assert 0.0 <= row["p_value"] <= 1.0
    assert json.dumps(data)


def test_ablation_writes_json(cfg: ArenaConfig, tmp_path: Path) -> None:
    report = run_ablation(
        arms()[:2],
        m0_skeleton(),
        cfg,
        parent_features=PARENT_SIG.features,
        seeds=range(3),
        resamples=100,
    )
    target = report.write(tmp_path / "ablation.json")
    assert json.loads(target.read_text(encoding="utf-8"))["seeds"] == 3


def test_ablation_requires_arms(cfg: ArenaConfig) -> None:
    with pytest.raises(ValueError):
        run_ablation([], m0_skeleton(), cfg)
