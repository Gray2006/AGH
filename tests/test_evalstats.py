from __future__ import annotations

import pytest

from agh.evalstats import Interval, cohens_d, holm, paired_bootstrap_ci


def test_interval_orders_bounds() -> None:
    ci = Interval(mean=0.5, lo=0.4, hi=0.6, n=100)
    assert ci.lo < ci.mean < ci.hi


def test_paired_bootstrap_ci_deterministic() -> None:
    diffs = [0.1, 0.12, 0.08, 0.15, 0.09, 0.11]
    a = paired_bootstrap_ci(diffs, resamples=500, seed=7)
    b = paired_bootstrap_ci(diffs, resamples=500, seed=7)
    assert a == b
    assert a.lo < a.mean < a.hi
    assert a.n == len(diffs)


def test_bootstrap_ci_excludes_zero_for_clear_effect() -> None:
    ci = paired_bootstrap_ci([0.5] * 30, resamples=300, seed=1)
    assert ci.lo > 0


def test_holm_orders_and_rejects() -> None:
    pvalues = [0.001, 0.01, 0.04, 0.5]
    decisions = holm(pvalues, alpha=0.05)
    rejected = [idx for idx, _thr, rej in decisions if rej]
    assert 0 in rejected and 1 in rejected
    assert 3 not in rejected
    # 阈值单调不减
    thresholds = [thr for _, thr, _ in decisions]
    assert thresholds == sorted(thresholds)


def test_holm_none_rejected_when_all_large() -> None:
    decisions = holm([0.4, 0.6, 0.9], alpha=0.05)
    assert not any(rej for _, _, rej in decisions)


def test_cohens_d_sign_and_magnitude() -> None:
    assert cohens_d([1.0, 1.1, 0.9], [0.0, 0.1, -0.1]) > 0
    assert cohens_d([0.0, 0.1], [1.0, 1.1]) < 0
    assert cohens_d([0.5, 0.5], [0.5, 0.5]) == 0.0
    with pytest.raises(ValueError):
        cohens_d([], [1.0])
