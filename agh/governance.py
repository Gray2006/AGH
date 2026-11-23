"""治理机（D10 / §3.3）。

八个状态：PROPOSED → VALIDATING → VERIFIED → RELEASED，另加 ROLLED_BACK /
SAFE_HALTED / QUARANTINED / RETIRED。

原规格「一切修改走八状态」会把技能固化卡死，所以按风险分级：
- T0：自动（带复验计数，可绕过人工）
- T1：自动验证后发布
- T2：必须人工批准
- 冻结层相关一律拒绝（连状态机都不让过）

劣化判定写成具体阈值与窗口，进冻结配置（D11）。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from .frozen import FrozenLayer, load_json

State = Literal[
    "PROPOSED",
    "VALIDATING",
    "VERIFIED",
    "RELEASED",
    "ROLLED_BACK",
    "SAFE_HALTED",
    "QUARANTINED",
    "RETIRED",
]

STATES: tuple[str, ...] = (
    "PROPOSED",
    "VALIDATING",
    "VERIFIED",
    "RELEASED",
    "ROLLED_BACK",
    "SAFE_HALTED",
    "QUARANTINED",
    "RETIRED",
)

TRANSITIONS: dict[str, set[str]] = {
    "PROPOSED": {"VALIDATING", "QUARANTINED", "SAFE_HALTED", "RETIRED"},
    "VALIDATING": {"VERIFIED", "PROPOSED", "QUARANTINED", "SAFE_HALTED"},
    "VERIFIED": {"RELEASED", "QUARANTINED", "SAFE_HALTED"},
    "RELEASED": {"ROLLED_BACK", "SAFE_HALTED", "RETIRED"},
    "ROLLED_BACK": {"RETIRED", "PROPOSED", "SAFE_HALTED"},
    "SAFE_HALTED": {"PROPOSED", "RETIRED"},
    "QUARANTINED": {"PROPOSED", "RETIRED"},
    "RETIRED": set(),
}

RiskTier = Literal["T0", "T1", "T2"]


class InvalidTransition(Exception):
    pass


class PendingApproval(Exception):
    """T2 变更等人工批准。"""


@dataclass
class GovernanceConfig:
    degrade_delta: float = 0.05
    degrade_window: int = 3
    consecutive_degrade: int = 2

    @classmethod
    def from_frozen(cls, frozen_root: Path) -> GovernanceConfig:
        raw = load_json(frozen_root, "thresholds.json")["governance"]
        return cls(
            degrade_delta=float(raw["degrade_delta"]),
            degrade_window=int(raw["degrade_window"]),
            consecutive_degrade=int(raw["consecutive_degrade"]),
        )


@dataclass
class TransitionRecord:
    from_state: str
    to_state: str
    tier: str
    revision: int
    reason: str


@dataclass
class GovernanceMachine:
    frozen: FrozenLayer | None
    config: GovernanceConfig = field(default_factory=GovernanceConfig)
    state: str = "PROPOSED"
    revision: int = 1
    history: list[TransitionRecord] = field(default_factory=list)
    recheck_count: dict[int, int] = field(default_factory=dict)
    _scores: list[float] = field(default_factory=list)
    _degrade_streak: int = 0

    def transition(
        self,
        to_state: str,
        *,
        tier: RiskTier = "T1",
        human_approved: bool = False,
        change_paths: Iterable[str | Path] = (),
        reason: str = "",
    ) -> str:
        if to_state not in STATES:
            raise InvalidTransition(f"未知状态: {to_state}")
        if self.frozen is not None:
            for path in change_paths:
                self.frozen.guard_write(Path(path))
        if to_state not in TRANSITIONS[self.state]:
            raise InvalidTransition(f"{self.state} → {to_state} 非法")

        if tier == "T2" and not human_approved:
            raise PendingApproval(f"T2 变更 {self.state} → {to_state} 需人工批准")
        if (
            tier == "T0"
            and to_state == "RELEASED"
            and self.recheck_count.get(self.revision, 0) < 1
        ):
            # T0 允许自动，但必须有复验计数
            raise InvalidTransition("T0 自动发布前必须至少复验一次")

        self.history.append(
            TransitionRecord(self.state, to_state, tier, self.revision, reason)
        )
        self.state = to_state
        return self.state

    def bump_recheck(self, revision: int | None = None) -> int:
        rev = revision if revision is not None else self.revision
        self.recheck_count[rev] = self.recheck_count.get(rev, 0) + 1
        return self.recheck_count[rev]

    def rollback(self, reason: str = "") -> str:
        return self.transition("ROLLED_BACK", tier="T1", reason=reason)

    def observe(self, score: float) -> bool:
        """监控劣化：连续两次窗口均值下降低于阈值 → SAFE_HALTED。

        已停车后重复调用返回 False，不重复记历史；记录里的 from_state 是停车前状态。
        """
        self._scores.append(score)
        w = self.config.degrade_window
        if len(self._scores) < 2 * w:
            return False
        if self.state == "SAFE_HALTED":
            return False
        recent = sum(self._scores[-w:]) / w
        previous = sum(self._scores[-2 * w : -w]) / w
        if previous - recent > self.config.degrade_delta:
            self._degrade_streak += 1
        else:
            self._degrade_streak = 0
        if self._degrade_streak >= self.config.consecutive_degrade:
            previous_state = self.state
            self.state = "SAFE_HALTED"
            self.history.append(
                TransitionRecord(
                    previous_state,
                    "SAFE_HALTED",
                    "T1",
                    self.revision,
                    f"连续劣化 {self._degrade_streak} 次（{previous:.3f}→{recent:.3f}）",
                )
            )
            return True
        return False
