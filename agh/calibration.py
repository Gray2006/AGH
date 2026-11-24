"""评分器校准：两个评分器是否一致、概率分数是否可信。

- Cohen's kappa：两个二值判断的一致度（扣掉随机一致）；
- ECE：把概率分数分箱后，与二值标签的偏差；
- agreement：直接一致率。
"""

from __future__ import annotations

from dataclasses import dataclass


def agreement(a: list[bool], b: list[bool]) -> float:
    if not a or len(a) != len(b):
        raise ValueError("样本为空或长度不一致")
    return sum(1 for x, y in zip(a, b, strict=False) if x == y) / len(a)


def cohen_kappa(a: list[bool], b: list[bool]) -> float:
    if not a or len(a) != len(b):
        raise ValueError("样本为空或长度不一致")
    n = len(a)
    po = sum(1 for x, y in zip(a, b, strict=False) if x == y) / n
    pa = sum(a) / n
    pb = sum(b) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    if pe == 1.0:
        return 1.0
    return (po - pe) / (1 - pe)


def ece(scores: list[float], labels: list[bool], bins: int = 5) -> float:
    """期望校准误差：每个箱里 |平均分 - 正例比例| 按样本数加权。"""
    if not scores or len(scores) != len(labels):
        raise ValueError("样本为空或长度不一致")
    total = len(scores)
    error = 0.0
    for index in range(bins):
        lo = index / bins
        hi = (index + 1) / bins
        members = [
            (s, y)
            for s, y in zip(scores, labels, strict=False)
            if (lo <= s < hi) or (index == bins - 1 and s == 1.0)
        ]
        if not members:
            continue
        avg = sum(s for s, _ in members) / len(members)
        pos = sum(1 for _, y in members if y) / len(members)
        error += len(members) / total * abs(avg - pos)
    return error


@dataclass
class CalibrationReport:
    n: int
    agreement: float
    kappa: float
    ece: float
    mean_a: float
    mean_b: float

    def as_dict(self) -> dict:
        return {
            "n": self.n,
            "agreement": round(self.agreement, 3),
            "cohen_kappa": round(self.kappa, 3),
            "ece": round(self.ece, 3),
            "mean_rater_a": round(self.mean_a, 3),
            "mean_rater_b": round(self.mean_b, 3),
        }


def evaluate(scores_a: list[float], scores_b: list[float], threshold: float = 0.5) -> CalibrationReport:
    labels_b = [b >= threshold for b in scores_b]
    return CalibrationReport(
        n=len(scores_a),
        agreement=agreement([a >= threshold for a in scores_a], labels_b),
        kappa=cohen_kappa([a >= threshold for a in scores_a], labels_b),
        ece=ece(scores_a, labels_b),
        mean_a=sum(scores_a) / len(scores_a),
        mean_b=sum(scores_b) / len(scores_b),
    )


__all__ = ["CalibrationReport", "agreement", "cohen_kappa", "ece", "evaluate"]
