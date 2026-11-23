from __future__ import annotations

import pytest

from agh.contracts import BudgetVector
from agh.ledger import BudgetExceeded, Ledger


class Clock:
    def __init__(self) -> None:
        self.now = 0

    def __call__(self) -> int:
        return self.now

    def advance(self, ms: int) -> None:
        self.now += ms


def test_reserve_and_settle() -> None:
    ledger = Ledger(BudgetVector(compute_units=100, wall_ms=1000, usd=1.0))
    lease = ledger.reserve(
        owner="c1", reserved=BudgetVector(compute_units=50, wall_ms=500, usd=0.5), max_tokens=100
    )
    assert ledger.snapshot().active_leases == 1
    ledger.settle(lease.lease_id, BudgetVector(compute_units=40, wall_ms=400, usd=0.4))
    snap = ledger.snapshot()
    assert snap.committed.usd == pytest.approx(0.4)
    assert snap.active_leases == 0
    assert snap.available.usd == pytest.approx(0.6)


def test_over_budget_reservation_rejected() -> None:
    ledger = Ledger(BudgetVector(compute_units=10, wall_ms=100, usd=0.1))
    with pytest.raises(BudgetExceeded):
        ledger.reserve(owner="c1", reserved=BudgetVector(compute_units=11, wall_ms=100, usd=0.1), max_tokens=10)


def test_reservation_idempotent_by_key() -> None:
    ledger = Ledger(BudgetVector(compute_units=100, wall_ms=1000, usd=1.0))
    a = ledger.reserve(
        owner="c1", reserved=BudgetVector(compute_units=10, wall_ms=10, usd=0.1), max_tokens=10, key="k"
    )
    b = ledger.reserve(
        owner="c1", reserved=BudgetVector(compute_units=10, wall_ms=10, usd=0.1), max_tokens=10, key="k"
    )
    assert a.lease_id == b.lease_id
    assert ledger.snapshot().active_leases == 1


def test_settle_idempotent() -> None:
    ledger = Ledger(BudgetVector(compute_units=100, wall_ms=1000, usd=1.0))
    lease = ledger.reserve(
        owner="c1", reserved=BudgetVector(compute_units=50, wall_ms=500, usd=0.5), max_tokens=10
    )
    ledger.settle(lease.lease_id, BudgetVector(compute_units=40, wall_ms=400, usd=0.4), key="s1")
    ledger.settle(lease.lease_id, BudgetVector(compute_units=40, wall_ms=400, usd=0.4), key="s1")
    assert ledger.snapshot().committed.usd == pytest.approx(0.4)


def test_settle_twice_without_key_does_not_double_bill() -> None:
    ledger = Ledger(BudgetVector(compute_units=100, wall_ms=1000, usd=1.0))
    lease = ledger.reserve(
        owner="c1", reserved=BudgetVector(compute_units=50, wall_ms=500, usd=0.5), max_tokens=10
    )
    ledger.settle(lease.lease_id, BudgetVector(compute_units=40, wall_ms=400, usd=0.4))
    ledger.settle(lease.lease_id, BudgetVector(compute_units=40, wall_ms=400, usd=0.4))
    assert ledger.snapshot().committed.usd == pytest.approx(0.4)


def test_over_reserved_records_violation() -> None:
    ledger = Ledger(BudgetVector(compute_units=100, wall_ms=1000, usd=1.0))
    lease = ledger.reserve(
        owner="c1", reserved=BudgetVector(compute_units=10, wall_ms=100, usd=0.1), max_tokens=10
    )
    ledger.settle(lease.lease_id, BudgetVector(compute_units=30, wall_ms=300, usd=0.3))
    snap = ledger.snapshot()
    assert snap.violations == 1
    assert snap.committed.usd == pytest.approx(0.3)


def test_reconcile_reclaims_expired_lease_and_is_idempotent() -> None:
    clock = Clock()
    ledger = Ledger(BudgetVector(compute_units=100, wall_ms=1000, usd=1.0), clock=clock, default_ttl_ms=1000)
    ledger.reserve(
        owner="c1", reserved=BudgetVector(compute_units=10, wall_ms=100, usd=0.1), max_tokens=10
    )
    clock.advance(500)
    assert ledger.reconcile() == []
    clock.advance(600)
    reclaimed = ledger.reconcile()
    assert len(reclaimed) == 1
    assert ledger.reconcile() == []  # 幂等
    assert ledger.snapshot().available.usd == pytest.approx(1.0)


def test_max_tokens_must_be_positive() -> None:
    ledger = Ledger(BudgetVector(compute_units=1, wall_ms=1, usd=1.0))
    with pytest.raises(ValueError):
        ledger.reserve(owner="c1", reserved=BudgetVector(compute_units=1, wall_ms=1, usd=0.1), max_tokens=0)

def test_over_reserved_checks_wall_ms() -> None:
    ledger = Ledger(BudgetVector(compute_units=100, wall_ms=1000, usd=1.0))
    lease = ledger.reserve(
        owner="c1", reserved=BudgetVector(compute_units=10, wall_ms=100, usd=0.1), max_tokens=10
    )
    ledger.settle(lease.lease_id, BudgetVector(compute_units=10, wall_ms=500, usd=0.1))
    assert ledger.snapshot().violations == 1
