from __future__ import annotations

from pathlib import Path

import pytest

from agh.frozen import FrozenLayer, FrozenLayerError
from agh.governance import (
    GovernanceConfig,
    GovernanceMachine,
    InvalidTransition,
    PendingApproval,
)


def config(frozen_src: Path) -> GovernanceConfig:
    return GovernanceConfig.from_frozen(frozen_src)


def test_happy_path_t1(frozen_src: Path) -> None:
    gov = GovernanceMachine(frozen=None, config=config(frozen_src))
    gov.transition("VALIDATING", tier="T1")
    gov.transition("VERIFIED", tier="T1")
    gov.transition("RELEASED", tier="T1")
    assert gov.state == "RELEASED"
    assert len(gov.history) == 3


def test_invalid_transition_raises(frozen_src: Path) -> None:
    gov = GovernanceMachine(frozen=None, config=config(frozen_src))
    with pytest.raises(InvalidTransition):
        gov.transition("RELEASED", tier="T1")


def test_t2_requires_human_approval(frozen_src: Path) -> None:
    gov = GovernanceMachine(frozen=None, config=config(frozen_src))
    gov.transition("VALIDATING", tier="T1")
    gov.transition("VERIFIED", tier="T1")
    with pytest.raises(PendingApproval):
        gov.transition("RELEASED", tier="T2", human_approved=False)
    gov.transition("RELEASED", tier="T2", human_approved=True)
    assert gov.state == "RELEASED"


def test_frozen_write_blocked_even_by_state_machine(
    frozen_root: Path, frozen_src: Path
) -> None:
    gov = GovernanceMachine(frozen=FrozenLayer(frozen_root), config=config(frozen_src))
    gov.transition("VALIDATING", tier="T1")
    gov.transition("VERIFIED", tier="T1")
    with pytest.raises(FrozenLayerError):
        gov.transition(
            "RELEASED",
            tier="T1",
            change_paths=[frozen_root / "thresholds.json"],
        )


def test_t0_auto_release_requires_recheck(frozen_src: Path) -> None:
    gov = GovernanceMachine(frozen=None, config=config(frozen_src))
    gov.transition("VALIDATING", tier="T0")
    gov.transition("VERIFIED", tier="T0")
    with pytest.raises(InvalidTransition):
        gov.transition("RELEASED", tier="T0")
    gov.bump_recheck()
    gov.transition("RELEASED", tier="T0")
    assert gov.state == "RELEASED"


def test_rollback_and_retire(frozen_src: Path) -> None:
    gov = GovernanceMachine(frozen=None, config=config(frozen_src))
    for state in ("VALIDATING", "VERIFIED", "RELEASED"):
        gov.transition(state, tier="T1")
    gov.rollback("质量事故")
    assert gov.state == "ROLLED_BACK"
    gov.transition("RETIRED", tier="T1")


def test_degrade_detection_halts(frozen_src: Path) -> None:
    gov = GovernanceMachine(frozen=None, config=config(frozen_src))
    gov.transition("VALIDATING", tier="T1")
    gov.transition("VERIFIED", tier="T1")
    gov.transition("RELEASED", tier="T1")
    w = gov.config.degrade_window
    for _ in range(w):
        assert not gov.observe(0.9)
    for _ in range(w):
        assert not gov.observe(0.5)  # 第一次窗口落差
    halted = False
    for _ in range(3 * w):
        halted = gov.observe(0.05) or halted
    assert halted
    assert gov.state == "SAFE_HALTED"

def test_halt_is_idempotent_and_records_real_from_state(frozen_src: Path) -> None:
    gov = GovernanceMachine(
        frozen=None,
        config=GovernanceConfig(degrade_window=1, consecutive_degrade=1, degrade_delta=0.05),
    )
    gov.transition("VALIDATING", tier="T1")
    assert not gov.observe(1.0)
    assert gov.observe(0.5)
    assert gov.observe(0.1) is False  # 已停车，不重复记录
    assert len(gov.history) == 2
    assert gov.history[-1].from_state == "VALIDATING"
    assert gov.history[-1].to_state == "SAFE_HALTED"
