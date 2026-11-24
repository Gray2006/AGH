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


def test_write_back_path(frozen_copy: Path) -> None:
    import json

    report = run_autonomous(
        frozen_copy,
        AutonomousConfig(rounds=1, generations=1, population=2, benchmarks=3, write_back=True),
    )
    assert report.written_back or report.rolled_back
    data = json.loads((frozen_copy / "thresholds.json").read_text(encoding="utf-8"))
    assert abs(sum(data["arena"]["weights"].values()) - 1.0) < 1e-6


def test_daemon_carries_params_between_rounds(frozen_src: Path, monkeypatch) -> None:
    """--no-write-back 也必须把上一轮参数带进下一轮，否则曲线是人工水平线。"""
    from types import SimpleNamespace

    from agh import autonomous as mod
    from agh.evolution_sharded import ParamGenome

    seen: list[dict[str, float]] = []
    made: list[ParamGenome] = []

    def fake_combined(benchmarks, cfg, evo_config, **kwargs):
        seen.append(dict(cfg.weights))
        genome = ParamGenome(
            weights={"confidence": 0.1, "structural": 0.1, "update": 0.0, "vertical": 0.3, "coverage": 0.5},
            dissent_tau=0.2,
        )
        made.append(genome)
        return SimpleNamespace(
            sharded=SimpleNamespace(mean_fitness=0.5 + 0.01 * len(seen)),
            best_params=genome,
            objective=None,
        )

    monkeypatch.setattr(mod, "combined_evolve", fake_combined)
    report = mod.run_autonomous(
        frozen_src,
        AutonomousConfig(rounds=2, generations=1, population=1, benchmarks=2, patience=5, write_back=False),
    )
    assert report.rounds_run == 2
    assert len(seen) == 2
    # 第二轮起始权重 = 第一轮返回的最优参数
    assert seen[1] == made[0].config(mod.ArenaConfig.from_frozen(frozen_src)).weights
    assert report.curve == [0.51, 0.52]


def test_daemon_fitness_uses_verifier(frozen_src: Path) -> None:
    """无验证器时种子顶在 coverage 权重；接验证器后应显著更高。"""
    import json

    cfg_data = json.loads((frozen_src / "thresholds.json").read_text(encoding="utf-8"))
    coverage = cfg_data["arena"]["weights"]["coverage"]
    report = run_autonomous(
        frozen_src,
        AutonomousConfig(rounds=1, generations=1, population=1, benchmarks=3, write_back=False),
    )
    assert report.curve[0] > coverage
