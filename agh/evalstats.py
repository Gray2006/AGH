"""评估统计（§4）。

预注册的检验方法落在冻结层；这里只提供实现：
- 配对 bootstrap 置信区间；
- Holm 校正（9 组消融）；
- Cohen's d 效应量。
不做「显著」的目测判断。
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Interval:
    mean: float
    lo: float
    hi: float
    n: int

    @property
    def excludes_zero(self) -> bool:
        return self.lo > 0 or self.hi < 0


def paired_bootstrap_ci(
    diffs: list[float] | np.ndarray,
    resamples: int = 10_000,
    ci_level: float = 0.95,
    seed: int = 0,
) -> Interval:
    arr = np.asarray(diffs, dtype=float)
    if arr.size == 0:
        raise ValueError("样本为空")
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, arr.size, size=(resamples, arr.size))
    means = arr[idx].mean(axis=1)
    alpha = (1.0 - ci_level) / 2.0
    lo, hi = np.quantile(means, [alpha, 1.0 - alpha])
    return Interval(mean=float(arr.mean()), lo=float(lo), hi=float(hi), n=int(arr.size))


def holm(pvalues: list[float], alpha: float = 0.05) -> list[tuple[int, float, bool]]:
    """返回 (原索引, 校正后阈值, 是否显著)，按 p 升序逐步判定。"""
    order = sorted(range(len(pvalues)), key=lambda i: pvalues[i])
    m = len(pvalues)
    out: list[tuple[int, float, bool]] = []
    rejected_so_far = True
    for rank, idx in enumerate(order):
        threshold = alpha / (m - rank)
        reject = rejected_so_far and pvalues[idx] <= threshold
        rejected_so_far = reject
        out.append((idx, threshold, reject))
    return out


def cohens_d(a: list[float], b: list[float]) -> float:
    x = np.asarray(a, dtype=float)
    y = np.asarray(b, dtype=float)
    nx, ny = x.size, y.size
    if nx < 2 or ny < 2:
        raise ValueError("每组至少 2 个样本")
    pooled = np.sqrt(((nx - 1) * x.var(ddof=1) + (ny - 1) * y.var(ddof=1)) / (nx + ny - 2))
    if pooled == 0:
        return 0.0
    return float((x.mean() - y.mean()) / pooled)
