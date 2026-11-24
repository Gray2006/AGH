from __future__ import annotations

import pytest

from agh.calibration import agreement, cohen_kappa, ece, evaluate


def test_agreement_and_kappa() -> None:
    a = [True, True, False, False, True]
    assert agreement(a, a) == pytest.approx(1.0)
    assert cohen_kappa(a, a) == pytest.approx(1.0)
    b = [False, False, True, True, False]
    assert agreement(a, b) == pytest.approx(0.0)
    assert cohen_kappa(a, b) < 0


def test_kappa_chance_level() -> None:
    a = [True, False, True, False]
    b = [True, False, False, True]
    # 一致率 0.5，碰巧一致 0.5 → kappa 0
    assert cohen_kappa(a, b) == pytest.approx(0.0)


def test_ece_perfect_and_off() -> None:
    assert ece([1.0, 1.0], [True, True]) == pytest.approx(0.0)
    assert ece([0.0, 0.0], [True, True]) == pytest.approx(1.0)


def test_evaluate_report() -> None:
    report = evaluate([1.0, 0.0, 1.0], [1.0, 0.0, 0.0])
    data = report.as_dict()
    assert data["n"] == 3
    assert 0.0 <= data["agreement"] <= 1.0
    assert data["cohen_kappa"] <= 1.0


def test_length_mismatch_raises() -> None:
    with pytest.raises(ValueError):
        agreement([True], [True, False])
