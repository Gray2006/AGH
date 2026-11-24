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
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from .arena import ArenaConfig
from .benchmarks import generate_benchmarks
from .calibration import cohen_kappa, ece
from .contracts import GestaltReconstruction, Skeleton
from .crypto import KeyRing
from .eventlog import EventLog
from .evolution import EvolutionConfig
from .evolution_sharded import ParamGenome, combined_evolve
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
    seed_degrade: float = 0.0
    hide_gold: bool = False
    replay_mutations: str | None = None
    failures: str | None = None


@dataclass
class AutonomousReport:
    rounds_run: int
    best_fitness: float
    curve: list[float]
    strategy_curve: list[float]
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
            "strategy_curve": [round(x, 5) for x in self.strategy_curve],
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



def _params_changed(frozen_cfg: ArenaConfig, params: ParamGenome) -> bool:
    """权重与 τ 与冻结层完全一致时，回写没有信息，只会重建锚点。"""
    current = {k: round(float(v), 4) for k, v in frozen_cfg.weights.items()}
    proposed = {k: round(float(v), 4) for k, v in params.weights.items()}
    if current != proposed:
        return True
    return round(float(params.dissent_tau), 3) != round(float(frozen_cfg.dissent_tau), 3)


def run_autonomous(
    frozen_root: Path,
    config: AutonomousConfig | None = None,
    log: EventLog | None = None,
) -> AutonomousReport:
    settings = config or AutonomousConfig()
    frozen_root = Path(frozen_root)
    notes: list[str] = []
    if settings.failures:
        from .failures import load_failures

        cases = load_failures(settings.failures)
        benchmarks = [case.to_benchmark() for case in cases]
        initial_carry = {case.skeleton.skeleton_id: case.seed for case in cases}
        notes.append(f"真实失败样本：{len(cases)} 条")
        if settings.seed_degrade:
            notes.append("失败样本自带种子，--seed-drop 被忽略")
        settings = replace(settings, seed_degrade=0.0)
    else:
        benchmarks = generate_benchmarks(settings.benchmarks, seed=settings.bench_seed)
        initial_carry = {}

    tokens_used = 0
    mutator_factory = None
    if settings.replay_mutations:
        from .evolution_llm import ReplayStrategyMutator

        records = [
            entry.payload
            for entry in EventLog(Path(settings.replay_mutations)).read()
            if entry.type == "llm.mutation"
        ]
        replay = ReplayStrategyMutator(records)

        def mutator_factory(feature_pool, node_pool):
            return replay

        notes.append(f"L1 重放：{len(records)} 条变异记录")
    elif settings.llm_mutator:
        from .evolution_llm import LlmStrategyMutator
        from .providers import make_client

        client = make_client(settings.provider, model=settings.model, api_key_env=settings.api_key_env)
        def record_mutation(payload: dict[str, Any]) -> None:
            if log is not None:
                log.append("llm.mutation", payload)

        class BudgetedMutator:
            def __init__(self, feature_pool, node_pool):
                self.inner = LlmStrategyMutator(
                    feature_pool,
                    node_pool,
                    complete=client,
                    recorder=record_mutation,
                )

            def mutate(self, parent, rng, name):
                nonlocal tokens_used
                if settings.daily_token_budget and tokens_used >= settings.daily_token_budget:
                    return self.inner.fallback.mutate(parent, rng, name)
                strategy = self.inner.mutate(parent, rng, name)
                usage = client.last_usage or {}
                tokens_used += int(usage.get("total_tokens", 0) or 0)
                return strategy

        mutator_factory = BudgetedMutator
    evo_config = EvolutionConfig(
        generations=settings.generations, population=settings.population, seed=settings.seed
    )

    best = -1.0
    curve: list[float] = []
    strategy_curve: list[float] = []
    stale = 0
    written = False
    rolled = False
    params: dict[str, Any] = {}
    rounds_run = 0
    # 参数在内存里跨轮延续：否则 --no-write-back 每轮都从冻结层重新起跑，
    # 曲线必然是一条水平线，观察模式就永远看不到「持续改进」。
    frozen_cfg = ArenaConfig.from_frozen(frozen_root)
    carried = ParamGenome.from_config(frozen_cfg)
    elite: dict[str, Any] = dict(initial_carry)

    for round_index in range(settings.rounds):
        rounds_run += 1
        cfg = carried.config(frozen_cfg)
        report = combined_evolve(
            benchmarks,
            cfg,
            evo_config,
            rounds=max(1, settings.generations),
            params_per_round=3,
            verifier=StructuralVerifier(),
            reference_cfg=frozen_cfg,
            seed_degrade=settings.seed_degrade,
            carry=elite,
            hide_gold=settings.hide_gold,
            mutator_factory=mutator_factory,
        )
        fitness = report.objective if report.objective is not None else report.sharded.mean_fitness
        carried = report.best_params
        elite = dict(getattr(report, "carry", {}) or {})
        curve.append(fitness)
        strategy_curve.append(report.sharded.mean_fitness)
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
            if not _params_changed(frozen_cfg, report.best_params):
                notes.append("参数与冻结层一致，跳过回写（写回同值只会重建锚点）")
            else:
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
        strategy_curve=strategy_curve,
        written_back=written,
        rolled_back=rolled,
        params=params,
        log_entries=len(log.read()) if log is not None else 0,
        tokens_used=tokens_used,
        notes=notes,
    )


__all__ = ["AutonomousConfig", "AutonomousReport", "calibration_ok", "run_autonomous"]
