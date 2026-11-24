"""把真实 token 用量折算成预算向量，接进账本。

预算原本记的是抽象单位，和实际花费脱钩。这里给出可配置的单价，
把 provider 返回的 usage 折算成 USD 与算力单位，供 Ledger 结算。
"""

from __future__ import annotations

from dataclasses import dataclass

from .contracts import BudgetVector


@dataclass(frozen=True)
class Price:
    """每百万 token 的价格（美元）。"""

    input_usd_per_mtok: float
    output_usd_per_mtok: float


DEFAULT_PRICES: dict[str, Price] = {
    "deepseek/deepseek-v4.1-flash": Price(0.28, 1.10),
    "deepseek-chat": Price(0.28, 1.10),
    "default": Price(1.0, 3.0),
}


def price_for(model: str) -> Price:
    return DEFAULT_PRICES.get(model, DEFAULT_PRICES["default"])


def usage_to_budget(
    usage: dict[str, int] | None,
    model: str = "default",
    *,
    price: Price | None = None,
    compute_units_per_ktok: float = 1.0,
) -> BudgetVector:
    """usage -> BudgetVector：usd 按单价折算，compute_units 按 token 量折算。"""
    if not usage:
        return BudgetVector()
    p = price or price_for(model)
    prompt = int(usage.get("prompt_tokens", 0) or 0)
    completion = int(usage.get("completion_tokens", 0) or 0)
    usd = (prompt / 1_000_000) * p.input_usd_per_mtok + (
        completion / 1_000_000
    ) * p.output_usd_per_mtok
    tokens = prompt + completion
    return BudgetVector(
        compute_units=round(tokens / 1000 * compute_units_per_ktok, 6),
        wall_ms=0,
        usd=round(usd, 6),
    )


__all__ = ["DEFAULT_PRICES", "Price", "price_for", "usage_to_budget"]
