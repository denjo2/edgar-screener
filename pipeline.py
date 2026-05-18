"""
Orchestration layer — combines the EDGAR client, XBRL parser, and AI calls
into two public functions:

    run_ticker(ticker)  — fetch, parse, screen, and optionally deep-dive one company
    run_batch(tickers)  — fetch + parse many companies, screen them in one API call

Everything network-related or AI-related is delegated to the layers below.
This file is the right place to add retry logic, caching, or progress callbacks.

Typical usage (see also cli.py):

    result = run_ticker("AAPL", run_screening=True, run_deep_dive=False)
    print(result.screening)

    results = run_batch(["AAPL", "MSFT", "GOOG"], run_screening=True)
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Optional

from ai.analyst import deep_dive
from ai.screener import screen_batch
from edgar.client import EdgarClient
from edgar.parser import parse_financials
from models import Financials, ScreeningResult


# ---------------------------------------------------------------------------
# Result containers
# ---------------------------------------------------------------------------

@dataclass
class TickerResult:
    """All outputs for a single ticker."""

    ticker: str
    cik: str
    financials: Financials

    # Populated only when run_screening=True
    screening: Optional[ScreeningResult] = None

    # Populated only when run_deep_dive=True
    deep_dive_memo: Optional[str] = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_ticker(
    ticker: str,
    *,
    run_screening: bool = True,
    run_deep_dive: bool = False,
    client: Optional[EdgarClient] = None,
) -> TickerResult:
    """
    Full pipeline for a single ticker.

    Args:
        ticker:        Stock symbol (e.g. "AAPL").
        run_screening: Run Stage 1 Claude screening and attach the result.
        run_deep_dive: Fetch the 10-K text and run Stage 2 Claude deep-dive.
        client:        Optional pre-constructed EdgarClient (useful in tests).

    Raises:
        ValueError if the ticker or XBRL facts cannot be found on EDGAR.
    """
    edgar = client or EdgarClient()

    cik = edgar.get_cik(ticker)
    if not cik:
        raise ValueError(f"No CIK found for ticker {ticker!r}")

    facts = edgar.get_company_facts(cik)
    if not facts:
        raise ValueError(f"No XBRL facts found for {ticker!r} (CIK {cik})")

    financials = parse_financials(ticker, facts)
    result = TickerResult(ticker=ticker, cik=cik, financials=financials)

    if run_screening:
        verdicts = screen_batch([financials])
        result.screening = verdicts[0] if verdicts else None

    if run_deep_dive:
        filing_text = edgar.get_10k_text(cik)
        if filing_text:
            company_name = facts.get("entityName", ticker)
            result.deep_dive_memo = deep_dive(company_name, ticker, filing_text)

    return result


def run_batch(
    tickers: list[str],
    *,
    run_screening: bool = True,
    client: Optional[EdgarClient] = None,
) -> list[TickerResult]:
    """
    Fetch + parse all tickers, then screen them in a single Claude call.

    Tickers that cannot be resolved or have no XBRL data are skipped with a
    warning to stderr. The returned list may be shorter than `tickers`.

    Deep-dive is not supported in batch mode — call run_ticker() individually
    for any PASS/WATCH companies after reviewing the batch results.

    Args:
        tickers:       List of stock symbols.
        run_screening: Send the full batch to Claude Sonnet for screening.
        client:        Optional pre-constructed EdgarClient.
    """
    edgar = client or EdgarClient()

    results: list[TickerResult] = []
    financials_list: list[Financials] = []

    for ticker in tickers:
        cik = edgar.get_cik(ticker)
        if not cik:
            print(f"[SKIP] {ticker}: no CIK found", file=sys.stderr)
            continue

        facts = edgar.get_company_facts(cik)
        if not facts:
            print(f"[SKIP] {ticker}: no XBRL facts (CIK {cik})", file=sys.stderr)
            continue

        f = parse_financials(ticker, facts)
        financials_list.append(f)
        results.append(TickerResult(ticker=ticker, cik=cik, financials=f))

    if run_screening and financials_list:
        verdicts = screen_batch(financials_list)
        # Build a lookup so order doesn't matter if Claude re-orders output.
        verdict_map = {v["ticker"]: v for v in verdicts}
        for r in results:
            r.screening = verdict_map.get(r.ticker)

    return results
