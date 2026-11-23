from __future__ import annotations

from pathlib import Path

import pytest

from agh.billing import BillingLedger, HttpBilling, JsonFileBilling, NullBilling
from agh.contracts import BudgetVector
from agh.ledger import Ledger


def test_json_billing_is_idempotent(tmp_path: Path) -> None:
    billing = JsonFileBilling(tmp_path / "receipts.jsonl", clock=lambda: 1000)
    first = billing.charge(0.5, "ref-1")
    second = billing.charge(0.5, "ref-1")
    assert first == second
    lines = (tmp_path / "receipts.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1


def test_json_billing_reloads_seen_refs(tmp_path: Path) -> None:
    path = tmp_path / "receipts.jsonl"
    JsonFileBilling(path, clock=lambda: 1).charge(0.2, "r")
    again = JsonFileBilling(path, clock=lambda: 2).charge(0.2, "r")
    assert again.issued_at_ms == 1


def test_billing_ledger_charges_once(tmp_path: Path) -> None:
    ledger = Ledger(BudgetVector(compute_units=100, wall_ms=1000, usd=1.0))
    billing = BillingLedger(ledger, JsonFileBilling(tmp_path / "r.jsonl"))
    lease = ledger.reserve(
        owner="c1", reserved=BudgetVector(compute_units=10, wall_ms=100, usd=0.1), max_tokens=10
    )
    settled, receipt = billing.settle(lease.lease_id, BudgetVector(compute_units=10, wall_ms=100, usd=0.1), key="k1")
    assert settled.usd == pytest.approx(0.1)
    assert receipt is not None and receipt.amount_usd == pytest.approx(0.1)
    _, again = billing.settle(lease.lease_id, BudgetVector(compute_units=10, wall_ms=100, usd=0.1), key="k1")
    assert again == receipt


def test_null_billing() -> None:
    receipt = NullBilling().charge(0.3, "x")
    assert receipt.amount_usd == pytest.approx(0.3)


def test_http_billing_with_fake_transport() -> None:
    def transport(method: str, url: str, payload: dict | None) -> dict:
        assert payload == {"amount_usd": 0.4, "ref": "r1"}
        return {"receipt_id": "rc-1", "provider": "remote", "amount_usd": 0.4, "issued_at_ms": 9}

    receipt = HttpBilling("https://billing.example/charge", transport=transport).charge(0.4, "r1")
    assert receipt.receipt_id == "rc-1"
    assert receipt.provider == "remote"
