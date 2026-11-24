from __future__ import annotations

from agh.governance_bench import (
    run_all,
    run_hashchain_experiment,
    run_ledger_experiment,
    run_provenance_experiment,
)


def test_provenance_catches_every_forgery() -> None:
    guarded, naive = run_provenance_experiment(rounds=10)
    assert guarded.attempts == 40
    assert guarded.caught == guarded.attempts
    assert guarded.catch_rate == 1.0
    assert naive.catch_rate == 0.0


def test_provenance_does_not_reject_legitimate_envelopes() -> None:
    guarded, _ = run_provenance_experiment(rounds=10)
    assert guarded.false_rejects == 0


def test_ledger_refuses_every_over_budget_call() -> None:
    guarded, naive = run_ledger_experiment(budget=10, calls=20)
    assert guarded.attempts == 10
    assert guarded.caught == 10
    assert naive.caught == 0


def test_hashchain_detects_tamper_every_time() -> None:
    guarded, naive = run_hashchain_experiment(rounds=10)
    assert guarded.attempts == 10
    assert guarded.caught == 10
    assert naive.caught == 0


def test_report_serializes() -> None:
    data = run_all(rounds=3).as_dict()
    assert set(data) == {"provenance", "ledger", "hashchain"}
    for section in data.values():
        for arm in section:
            assert 0.0 <= arm["catch_rate"] <= 1.0
