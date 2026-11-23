"""Python SDK：把 M0 链路包成可嵌入的客户端。

```python
from agh.sdk import AghClient

client = AghClient()
report = client.run()
assert client.verify_log()
assert client.replay().bit_exact
```
"""

from __future__ import annotations

from pathlib import Path

from .arena import ArenaConfig
from .crypto import KeyRing
from .eventlog import EventLog, L1Replay, ReplayReport
from .experiment import Arm, ExperimentReport, run_experiment
from .llm import RuleChild
from .pipeline import (
    DEV_KID,
    DEV_SECRET,
    INITIAL_STATE,
    PARENT_SIG,
    M0Report,
    dissent_child,
    faithful_child,
    m0_reducer,
    m0_skeleton,
    run_m0,
    shallow_child,
)


def default_frozen_root() -> Path:
    return Path(__file__).resolve().parents[1] / "config" / "frozen"


class AghClient:
    def __init__(
        self,
        frozen_root: str | Path | None = None,
        run_dir: str | Path | None = None,
        keyring: KeyRing | None = None,
        kid: str = DEV_KID,
    ) -> None:
        self.frozen_root = Path(frozen_root) if frozen_root else default_frozen_root()
        self.run_dir = Path(run_dir) if run_dir else Path("runs") / "m0"
        self.keyring = keyring or KeyRing.with_secret(DEV_KID, DEV_SECRET)
        self.kid = kid

    def run(self, *, include_dissent: bool = True, human_approved: bool = True) -> M0Report:
        return run_m0(
            frozen_root=self.frozen_root,
            run_dir=self.run_dir,
            include_dissent=include_dissent,
            human_approved=human_approved,
        )

    def _log(self) -> EventLog:
        return EventLog(self.run_dir / "events.jsonl")

    def verify_log(self) -> bool:
        from .eventlog import LogTampered

        try:
            self._log().verify()
            return True
        except LogTampered:
            return False

    def replay(self) -> ReplayReport:
        return L1Replay(self._log(), m0_reducer, INITIAL_STATE).run()

    def _cfg(self) -> ArenaConfig:
        return ArenaConfig.from_frozen(self.frozen_root)

    def _arms(self) -> list[Arm]:
        return [
            Arm("faithful", RuleChild("faithful", faithful_child)),
            Arm("dissent", RuleChild("dissent", dissent_child)),
            Arm("shallow", RuleChild("shallow", shallow_child)),
        ]

    def experiment(self, *, seeds: int = 100, resamples: int = 2_000) -> ExperimentReport:
        return run_experiment(
            self._arms(),
            m0_skeleton(),
            self._cfg(),
            parent_features=PARENT_SIG.features,
            seeds=range(seeds),
            resamples=resamples,
        )

    def ablation(self, *, seeds: int = 50, resamples: int = 2_000):
        from .ablation import run_ablation

        return run_ablation(
            self._arms(),
            m0_skeleton(),
            self._cfg(),
            parent_features=PARENT_SIG.features,
            seeds=range(seeds),
            resamples=resamples,
        )


__all__ = ["AghClient", "default_frozen_root"]
