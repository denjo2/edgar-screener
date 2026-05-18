"""
Data models shared across the whole project.

Two types:
  Financials  — the structured output of the XBRL parser. Passed to the AI layer.
  ScreeningResult — the structured output returned by the Stage 1 Claude call.

Keeping models in one file means you can see the full data contract at a glance
and edit field names / types in one place.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# XBRL financial data (Stage 1 input)
# ---------------------------------------------------------------------------

@dataclass
class Financials:
    """
    All financial data extracted for one company.

    Balance-sheet fields are point-in-time (most recent filing date).
    *_ttm fields are trailing-twelve-months, either from the most recent
    10-K or stitched from four consecutive 10-Q quarters.

    ticker is required so Stage 1 can echo it back in the JSON verdict.
    """

    ticker: str

    # ---- Balance sheet (instant / point-in-time) -------------------------
    total_assets: Optional[float] = None
    total_liabilities: Optional[float] = None
    stockholders_equity: Optional[float] = None
    current_assets: Optional[float] = None
    current_liabilities: Optional[float] = None
    cash: Optional[float] = None
    goodwill: float = 0.0
    intangibles: float = 0.0

    # Debt components kept separate so analysts can audit the total.
    long_term_debt: float = 0.0
    long_term_debt_current: float = 0.0  # current portion of LT debt
    short_term_borrowings: float = 0.0
    total_debt: float = 0.0              # sum of the three lines above

    shares_outstanding: Optional[float] = None

    # ---- Income statement / cash flow (TTM duration) ---------------------
    revenue_ttm: Optional[float] = None
    gross_profit_ttm: Optional[float] = None
    operating_income_ttm: Optional[float] = None
    net_income_ttm: Optional[float] = None
    ocf_ttm: Optional[float] = None     # operating cash flow
    capex_ttm: Optional[float] = None   # capital expenditures (positive = outflow)

    # ---- Derived metrics (computed by the parser) ------------------------
    tangible_book_value: Optional[float] = None
    ncav: Optional[float] = None            # net current asset value
    fcf_ttm: Optional[float] = None         # free cash flow = OCF - capex
    current_ratio: Optional[float] = None
    debt_to_equity: Optional[float] = None
    net_cash_position: Optional[float] = None
    gross_margin_ttm: Optional[float] = None
    operating_margin_ttm: Optional[float] = None

    def to_dict(self) -> dict:
        """Serialize to plain dict for JSON serialization."""
        return asdict(self)


# ---------------------------------------------------------------------------
# Stage 1 screening output (returned by the Claude screener)
# ---------------------------------------------------------------------------

# Using plain dicts with type hints (TypedDict style) rather than a dataclass
# because the model returns JSON that we parse directly — no constructor needed.

class KeyMetrics(dict):
    """
    Subset of Financials echoed back in the Stage 1 verdict so the reader
    doesn't have to cross-reference the full financials dict.

    Keys: current_ratio, debt_to_equity, operating_margin_ttm,
          fcf_ttm, ncav, net_cash_position.
    Values: float | None.
    """


class ScreeningResult(dict):
    """
    One element from the Stage 1 JSON array.

    Keys:
        ticker          str   — company identifier
        verdict         str   — PASS | WATCH | FAIL | NEUTRAL
        primary_reason  str   — single sentence driving the verdict
        flags           list  — short strings naming each triggered rule
        key_metrics     dict  — KeyMetrics subset
    """
