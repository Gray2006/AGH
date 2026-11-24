"""自主迭代守护：定时跑进化 → 门禁校验 → 回写冻结层 → 失败回滚。

默认零 token：只用规则变异器与本地打分。LLM 变异器需显式传入。
安全边界：
- 只回写 arena 权重与 dissent_tau，不碰代码；
- 回写前跑校准回归（ECE/κ 门限），失败就恢复备份并重建锚点；
- 连续 patience 轮无改进即停，不空转。
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .arena import ArenaConfig
from .benchmarks import generate_benchmarks
from .calibration import cohen_kappa, ece
from .contracts import GestaltReconstruction, Skeleton
from .crypto import KeyRing
from .eventlog import EventLog
from .evolution import EvolutionConfig
from .evolution_sharded import combined_evolve
from .frozen import FrozenLayer
from .pipeline import DEV_KID, DEV_SECRET
from .verifier import StructuralVerifier

CALIBRATION_FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "calibration.json"
MAX_ECE = 0.05
MIN_KAPPA = 0.9


@dataclass
class AutonomousConfig:
    rounds: int = 4
    generations: int = 2
    population: int = 2
    benchmarks: int = 6
    bench_seed: int = 0
    patience: int = 2
    min_improvement: float = 1e-4
    write_back: bool = True
    seed: int = 0
    llm_mutator: bool = False
    provider: str = "deepseek"
    model: str | None = None
    api_key_env: str | None = None
    daily_token_budget: int = 0


@dataclass
class AutonomousReport:
    rounds_run: int
    best_fitness: float
    curve: list[float]
    written_back: bool
    rolled_back: bool
    params: dict[str, Any]
    log_entries: int
    tokens_used: int = 0
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "rounds_run": self.rounds_run,
            "best_fitness": round(self.best_fitness, 5),
            "curve": [round(x, 5) for x in self.curve],
            "written_back": self.written_back,
            "rolled_back": self.rolled_back,
            "params": self.params,
            "log_entries": self.log_entries,
            "tokens_used": self.tokens_used,
            "notes": self.notes,
        }


def calibration_ok() -> tuple[bool, str]:
    if not CALIBRATION_FIXTURE.exists():
        return True, "无校准样本，跳过"
    items = json.loads(CALIBRATION_FIXTURE.read_text(encoding="utf-8"))
    verifier = StructuralVerifier()
    machine: list[float] = []
    human: list[float] = []
    for item in items:
        skeleton = Skeleton.model_validate(item["skeleton"])
        recon = GestaltReconstruction.model_validate(item["reconstruction"])
        machine.append(verifier.score(recon, skeleton))
        human.append(float(item["label"]))
    current_ece = ece(machine, human)
    kappa = cohen_kappa([m >= 0.99 for m in machine], [h >= 0.99 for h in human])
    if current_ece > MAX_ECE or kappa < MIN_KAPPA:
        return False, f"校准不达标: ECE {current_ece:.3f}, κ {kappa:.3f}"
    return True, "校准通过"


def _write_back(frozen_root: Path, weights: dict[str, float], dissent_tau: float) -> None:
    path = frozen_root / "thresholds.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["arena"]["weights"] = {k: round(v, 4) for k, v in weights.items()}
    data["arena"]["dissent_tau"] = round(dissent_tau, 3)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _reanchor(frozen_root: Path) -> None:
    keyring = KeyRing.with_secret(DEV_KID, DEV_SECRET)
    FrozenLayer(frozen_root).write_anchor(frozen_root.parent / "anchor.json", keyring, DEV_KID)


def run_autonomous(
    frozen_root: Path,
    config: AutonomousConfig | None = None,
    log: EventLog | None = None,
) -> AutonomousReport:
    settings = config or AutonomousConfig()
    frozen_root = Path(frozen_root)
    notes: list[str] = []
    benchmarks = generate_benchmarks(settings.benchmarks, seed=settings.bench_seed)

    tokens_used = 0
    active_mutator = None
    if settings.llm_mutator:
        from .evolution_llm import LlmStrategyMutator
        from .providers import make_client

        client = make_client(settings.provider, model=settings.model, api_key_env=settings.api_key_env)
        feature_pool = sorted({f"{a}-{b}" for bench in benchmarks for a, b in bench.skeleton.edges})
        node_pool = sorted({n for bench in benchmarks for n in bench.skeleton.nodes})
        base_mutator = LlmStrategyMutator(feature_pool, node_pool, complete=client)

        class BudgetedMutator:
            def mutate(self, parent, rng, name):
                nonlocal tokens_used
                if settings.daily_token_budget and tokens_used >= settings.daily_token_budget:
                    return base_mutator.fallback.mutate(parent, rng, name)
                strategy = base_mutator.mutate(parent, rng, name)
                usage = client.last_usage or {}
                tokens_used += int(usage.get("total_tokens", 0) or 0)
                return strategy

        active_mutator = BudgetedMutator()
    evo_config = EvolutionConfig(
        generations=settings.generations, population=settings.population, seed=settings.seed
    )

    best = -1.0
    curve: list[float] = []
    stale = 0
    written = False
    rolled = False
    params: dict[str, Any] = {}
    rounds_run = 0

    for round_index in range(settings.rounds):
        rounds_run += 1
        cfg = ArenaConfig.from_frozen(frozen_root)
        report = combined_evolve(
            benchmarks, cfg, evo_config, rounds=1, params_per_round=2, mutator=active_mutator
        )
        fitness = report.sharded.mean_fitness
        curve.append(fitness)
        params = report.best_params.as_dict()
        if log is not None:
            log.append(
                "autonomous.round",
                {"round": round_index, "fitness": fitness, "params": params},
            )
        if fitness > best + settings.min_improvement:
            best = fitness
            stale = 0
        else:
            stale += 1
            if stale >= settings.patience:
                notes.append(f"连续 {stale} 轮无改进，停止")
                break

        if settings.daily_token_budget and tokens_used >= settings.daily_token_budget:
            notes.append(f"token 预算用尽（{tokens_used}），停止")
            break

        if settings.write_back and fitness > 0:
            backup = frozen_root / "thresholds.json.bak"
            shutil.copy2(frozen_root / "thresholds.json", backup)
            _write_back(frozen_root, report.best_params.weights, report.best_params.dissent_tau)
            ok, detail = calibration_ok()
            if not ok:
                shutil.copy2(backup, frozen_root / "thresholds.json")
                _reanchor(frozen_root)
                rolled = True
                notes.append(f"回写被回滚：{detail}")
            else:
                _reanchor(frozen_root)
                written = True
                notes.append(f"回写成功：{detail}")

    return AutonomousReport(
        rounds_run=rounds_run,
        best_fitness=best if best >= 0 else (curve[-1] if curve else 0.0),
        curve=curve,
        written_back=written,
        rolled_back=rolled,
        params=params,
        log_entries=len(log.read()) if log is not None else 0,
        tokens_used=tokens_used,
        notes=notes,
    )


__all__ = ["AutonomousConfig", "AutonomousReport", "calibration_ok", "run_autonomous"]
