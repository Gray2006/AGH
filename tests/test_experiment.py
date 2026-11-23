from __future__ import annotations

import json
from pathlib import Path

import pytest

from agh.arena import ArenaConfig
from agh.experiment import Arm, run_experiment
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


def test_experiment_runs_and_reports(cfg: ArenaConfig) -> None:
    report = run_experiment(
        arms(),
        m0_skeleton(),
        cfg,
        contract_id="ct-exp",
        parent_features=PARENT_SIG.features,
        seeds=range(8),
        resamples=200,
    )
    data = report.as_dict()
    assert data["seeds"] == 8
    assert len(data["arms"]) == 3
    by_name = {a["name"]: a for a in data["arms"]}
    assert by_name["faithful"]["valid"] == 8
    assert by_name["shallow"]["errors"] == 8  # 硬过滤拒收
    assert by_name["faithful"]["wins"] >= 1
    assert 0.0 <= data["contested_rate"] <= 1.0
    assert json.dumps(data)  # 可序列化


def test_experiment_comparisons_have_bounds(cfg: ArenaConfig) -> None:
    report = run_experiment(
        arms(),
        m0_skeleton(),
        cfg,
        parent_features=PARENT_SIG.features,
        seeds=range(10),
        resamples=300,
    )
    assert report.comparisons
    for comparison in report.comparisons:
        assert comparison.delta.lo <= comparison.delta.mean <= comparison.delta.hi
        assert 0.0 <= comparison.p_value <= 1.0
        assert comparison.holm_threshold > 0


def test_experiment_writes_json(cfg: ArenaConfig, tmp_path: Path) -> None:
    report = run_experiment(
        arms()[:2],
        m0_skeleton(),
        cfg,
        parent_features=PARENT_SIG.features,
        seeds=range(4),
        resamples=100,
    )
    target = report.write(tmp_path / "experiment.json")
    assert target.exists()
    assert json.loads(target.read_text(encoding="utf-8"))["seeds"] == 4


def test_experiment_requires_arms(cfg: ArenaConfig) -> None:
    with pytest.raises(ValueError):
        run_experiment([], m0_skeleton(), cfg)
