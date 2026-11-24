from __future__ import annotations

from pathlib import Path

from agh.failures import dump_failures, failures_to_benchmarks, load_failures

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "real_failures.json"


def test_fixture_loads() -> None:
    cases = load_failures(FIXTURE)
    assert len(cases) >= 1
    for case in cases:
        assert case.seed.features
        assert case.failed_score < 1.0
        bench = case.to_benchmark()
        assert bench.skeleton.skeleton_id == case.skeleton.skeleton_id
        assert bench.parent.features == [f"{a}-{b}" for a, b in case.skeleton.edges]


def test_roundtrip(tmp_path: Path) -> None:
    cases = load_failures(FIXTURE)
    out = tmp_path / "cases.json"
    dump_failures(cases, out)
    again = load_failures(out)
    assert [c.as_dict() for c in cases] == [c.as_dict() for c in again]


def test_failures_to_benchmarks() -> None:
    cases = load_failures(FIXTURE)
    benches = failures_to_benchmarks(cases)
    assert len(benches) == len(cases)


def test_daemon_uses_failure_seeds(monkeypatch, frozen_copy: Path) -> None:
    from types import SimpleNamespace

    from agh import autonomous as mod

    cases = load_failures(FIXTURE)
    seen: dict[str, object] = {}

    def fake_combined(benchmarks, cfg, evo_config, **kwargs):
        seen.update(kwargs.get("carry") or {})
        return SimpleNamespace(
            objective=0.5,
            best_params=mod.ParamGenome.from_config(cfg),
            carry={},
            sharded=SimpleNamespace(mean_fitness=0.5),
        )

    monkeypatch.setattr(mod, "combined_evolve", fake_combined)
    report = mod.run_autonomous(
        frozen_copy,
        mod.AutonomousConfig(rounds=1, generations=1, population=1, failures=str(FIXTURE)),
    )
    for case in cases:
        assert seen[case.skeleton.skeleton_id].features == case.seed.features  # type: ignore[union-attr]
    assert any("真实失败样本" in note for note in report.notes)
