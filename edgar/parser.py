"""
XBRL financial parser.

Turns the raw CompanyFacts JSON from EDGAR into a typed Financials dataclass.

Two concept types require different aggregation strategies:
  Instant concepts  — balance sheet; take the single most recent value.
  Duration concepts — income statement / cash flow; compute TTM (see ttm_duration).

The sets below control which concepts are extracted. Adding a new metric is a
two-step edit: add the concept name here, then add a field to Financials in
models.py and wire it up in parse_financials().
"""

from datetime import datetime
from typing import Optional

from models import Financials


# ---------------------------------------------------------------------------
# Concept registries
# ---------------------------------------------------------------------------

# Balance-sheet items: point-in-time, keyed on the filing's `end` date.
INSTANT_CONCEPTS: set[str] = {
    "Assets",
    "AssetsCurrent",
    "Liabilities",
    "LiabilitiesCurrent",
    "StockholdersEquity",
    "CashAndCashEquivalentsAtCarryingValue",
    "Goodwill",
    "IntangibleAssetsNetExcludingGoodwill",
    "LongTermDebt",
    "LongTermDebtCurrent",
    "ShortTermBorrowings",
    "CommonStockSharesOutstanding",
}

# Income-statement / cash-flow items: period-length matters; we compute TTM.
DURATION_CONCEPTS: set[str] = {
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",  # ASC 606 variant
    "GrossProfit",
    "OperatingIncomeLoss",
    "NetIncomeLoss",
    "NetCashProvidedByUsedInOperatingActivities",
    "PaymentsToAcquirePropertyPlantAndEquipment",
    "EarningsPerShareBasic",
}


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _entries(us_gaap: dict, concept: str) -> list[dict]:
    """
    Return all 10-K/10-Q entries for a concept, regardless of unit type.

    Tries USD first (monetary), then USD/shares (EPS), then shares (share
    counts), then pure (ratios). Stops at the first non-empty match so we
    don't mix unit types.
    """
    if concept not in us_gaap:
        return []
    units = us_gaap[concept].get("units", {})
    for unit_type in ("USD", "USD/shares", "shares", "pure"):
        if unit_type in units:
            return [
                e for e in units[unit_type]
                if e.get("form") in ("10-K", "10-Q") and "end" in e
            ]
    return []


def latest_instant(us_gaap: dict, concept: str) -> Optional[float]:
    """Most recent point-in-time value, sorted by `end` date descending."""
    entries = _entries(us_gaap, concept)
    if not entries:
        return None
    entries.sort(key=lambda e: e["end"], reverse=True)
    return entries[0].get("val")


def ttm_duration(us_gaap: dict, concept: str) -> Optional[float]:
    """
    Compute trailing-twelve-months for a duration concept.

    Strategy (in preference order):
      1. If the most recent entry covers ~365 days (350–380), it's an annual
         (10-K) — return it directly.
      2. Otherwise stitch the four most recent non-overlapping quarterly
         entries (80–100 days each) whose combined span is ~365 days.

    Returns None rather than an approximation when neither path works.
    This is intentional: downstream callers treat None as "data unavailable"
    rather than zero or an incorrect sum.
    """
    entries = _entries(us_gaap, concept)
    if not entries:
        return None

    parsed = []
    for e in entries:
        try:
            start = datetime.fromisoformat(e["start"])
            end = datetime.fromisoformat(e["end"])
            days = (end - start).days
            parsed.append({"start": start, "end": end, "days": days, "val": e["val"]})
        except (KeyError, ValueError):
            continue

    if not parsed:
        return None

    parsed.sort(key=lambda x: x["end"], reverse=True)

    # Path 1: most recent entry is an annual filing.
    # 350–380 days covers both calendar-year and 52/53-week fiscal years.
    if 350 <= parsed[0]["days"] <= 380:
        return parsed[0]["val"]

    # Path 2: stitch four consecutive non-overlapping quarters.
    quarterly = [p for p in parsed if 80 <= p["days"] <= 100]
    if len(quarterly) < 4:
        return None

    selected: list[dict] = []
    last_start = None
    for q in quarterly:
        if last_start is None or q["end"] <= last_start:
            selected.append(q)
            last_start = q["start"]
        if len(selected) == 4:
            break

    if len(selected) != 4:
        return None

    total_days = sum(q["days"] for q in selected)
    if not (350 <= total_days <= 380):
        return None

    return sum(q["val"] for q in selected)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def parse_financials(ticker: str, facts: dict) -> Financials:
    """
    Extract and derive all financial metrics from a CompanyFacts JSON blob.

    `ticker` is passed through to Financials.ticker so Stage 1 can echo it
    back in the screening verdict.
    """
    us_gaap = facts.get("facts", {}).get("us-gaap", {})

    # -- Instant (balance sheet) ------------------------------------------
    total_assets        = latest_instant(us_gaap, "Assets")
    total_liabilities   = latest_instant(us_gaap, "Liabilities")
    stockholders_equity = latest_instant(us_gaap, "StockholdersEquity")
    current_assets      = latest_instant(us_gaap, "AssetsCurrent")
    current_liabilities = latest_instant(us_gaap, "LiabilitiesCurrent")
    cash                = latest_instant(us_gaap, "CashAndCashEquivalentsAtCarryingValue")
    goodwill            = latest_instant(us_gaap, "Goodwill") or 0.0
    intangibles         = latest_instant(us_gaap, "IntangibleAssetsNetExcludingGoodwill") or 0.0
    shares_outstanding  = latest_instant(us_gaap, "CommonStockSharesOutstanding")

    lt_debt         = latest_instant(us_gaap, "LongTermDebt") or 0.0
    lt_debt_current = latest_instant(us_gaap, "LongTermDebtCurrent") or 0.0
    st_borrowings   = latest_instant(us_gaap, "ShortTermBorrowings") or 0.0
    total_debt      = lt_debt + lt_debt_current + st_borrowings

    # -- Duration (TTM) ---------------------------------------------------
    # Revenue can be tagged under either concept depending on ASC 606 adoption.
    revenue_ttm = (
        ttm_duration(us_gaap, "Revenues")
        or ttm_duration(us_gaap, "RevenueFromContractWithCustomerExcludingAssessedTax")
    )
    gross_profit_ttm      = ttm_duration(us_gaap, "GrossProfit")
    operating_income_ttm  = ttm_duration(us_gaap, "OperatingIncomeLoss")
    net_income_ttm        = ttm_duration(us_gaap, "NetIncomeLoss")
    ocf_ttm               = ttm_duration(us_gaap, "NetCashProvidedByUsedInOperatingActivities")
    # PaymentsToAcquirePropertyPlantAndEquipment is reported as a positive outflow.
    capex_ttm             = ttm_duration(us_gaap, "PaymentsToAcquirePropertyPlantAndEquipment")

    # -- Derived ----------------------------------------------------------
    tangible_book = (
        stockholders_equity - goodwill - intangibles
        if stockholders_equity is not None else None
    )
    ncav = (
        current_assets - total_liabilities
        if current_assets is not None and total_liabilities is not None else None
    )
    fcf_ttm = (
        ocf_ttm - capex_ttm
        if ocf_ttm is not None and capex_ttm is not None else None
    )
    current_ratio = (
        current_assets / current_liabilities
        if current_assets and current_liabilities else None
    )
    debt_to_equity = (
        total_debt / stockholders_equity
        if stockholders_equity and stockholders_equity > 0 else None
    )
    net_cash = cash - total_debt if cash is not None else None
    gross_margin = (
        gross_profit_ttm / revenue_ttm
        if gross_profit_ttm is not None and revenue_ttm else None
    )
    operating_margin = (
        operating_income_ttm / revenue_ttm
        if operating_income_ttm is not None and revenue_ttm else None
    )

    return Financials(
        ticker=ticker,
        total_assets=total_assets,
        total_liabilities=total_liabilities,
        stockholders_equity=stockholders_equity,
        current_assets=current_assets,
        current_liabilities=current_liabilities,
        cash=cash,
        goodwill=goodwill,
        intangibles=intangibles,
        long_term_debt=lt_debt,
        long_term_debt_current=lt_debt_current,
        short_term_borrowings=st_borrowings,
        total_debt=total_debt,
        shares_outstanding=shares_outstanding,
        revenue_ttm=revenue_ttm,
        gross_profit_ttm=gross_profit_ttm,
        operating_income_ttm=operating_income_ttm,
        net_income_ttm=net_income_ttm,
        ocf_ttm=ocf_ttm,
        capex_ttm=capex_ttm,
        tangible_book_value=tangible_book,
        ncav=ncav,
        fcf_ttm=fcf_ttm,
        current_ratio=current_ratio,
        debt_to_equity=debt_to_equity,
        net_cash_position=net_cash,
        gross_margin_ttm=gross_margin,
        operating_margin_ttm=operating_margin,
    )
