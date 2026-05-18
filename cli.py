"""
Command-line interface.

Subcommands:
    screen   — fetch financials and run Stage 1 screening (single or batch)
    deepdive — fetch 10-K and run Stage 2 deep-dive analysis (single ticker)
    fetch    — pull and print XBRL financials only (no AI, good for debugging)

Usage examples:

    # Screen one ticker and print the JSON verdict
    python cli.py screen AAPL

    # Screen a list of tickers and include full financials in output
    python cli.py screen AAPL MSFT GOOG --verbose

    # Screen tickers from a file (one per line)
    python cli.py screen --file tickers.txt

    # Deep-dive (requires ANTHROPIC_API_KEY and fetches the 10-K)
    python cli.py deepdive AAPL

    # Inspect raw XBRL data without calling Claude
    python cli.py fetch AAPL
"""

import argparse
import json
import sys
from dataclasses import asdict

from pipeline import run_batch, run_ticker


# ---------------------------------------------------------------------------
# Sub-command handlers
# ---------------------------------------------------------------------------

def cmd_screen(args: argparse.Namespace) -> None:
    tickers = _resolve_tickers(args)

    if len(tickers) == 1:
        result = run_ticker(tickers[0], run_screening=True, run_deep_dive=False)
        results = [result]
    else:
        results = run_batch(tickers, run_screening=True)

    output = []
    for r in results:
        entry: dict = {
            "ticker": r.ticker,
            "cik": r.cik,
            "screening": r.screening,
        }
        if args.verbose:
            entry["financials"] = asdict(r.financials)
        output.append(entry)

    print(json.dumps(output, indent=2, default=str))


def cmd_deepdive(args: argparse.Namespace) -> None:
    result = run_ticker(
        args.ticker,
        run_screening=False,
        run_deep_dive=True,
    )
    if result.deep_dive_memo:
        print(result.deep_dive_memo)
    else:
        print(f"Error: no 10-K filing found for {args.ticker}", file=sys.stderr)
        sys.exit(1)


def cmd_fetch(args: argparse.Namespace) -> None:
    result = run_ticker(args.ticker, run_screening=False, run_deep_dive=False)
    print(json.dumps(asdict(result.financials), indent=2, default=str))


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="edgar-screener",
        description="SEC EDGAR microcap value screener powered by Claude.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ---- screen ------------------------------------------------------------
    p_screen = sub.add_parser(
        "screen",
        help="Run Stage 1 batch screening (Claude Sonnet)",
        description="Fetch XBRL financials and screen one or more companies.",
    )
    p_screen.add_argument(
        "tickers",
        nargs="*",
        metavar="TICKER",
        help="One or more stock symbols (e.g. AAPL MSFT).",
    )
    p_screen.add_argument(
        "--file", "-f",
        metavar="FILE",
        help="Path to a file with one ticker per line.",
    )
    p_screen.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Include full Financials dict in JSON output.",
    )
    p_screen.set_defaults(func=cmd_screen)

    # ---- deepdive ----------------------------------------------------------
    p_dive = sub.add_parser(
        "deepdive",
        help="Run Stage 2 deep-dive on one ticker (Claude Opus)",
        description="Fetch the most recent 10-K and produce a structured analyst memo.",
    )
    p_dive.add_argument(
        "ticker",
        metavar="TICKER",
        help="Stock symbol (e.g. AAPL).",
    )
    p_dive.set_defaults(func=cmd_deepdive)

    # ---- fetch -------------------------------------------------------------
    p_fetch = sub.add_parser(
        "fetch",
        help="Fetch and print XBRL financials only (no AI)",
        description="Pull raw EDGAR data and print the parsed Financials as JSON.",
    )
    p_fetch.add_argument(
        "ticker",
        metavar="TICKER",
        help="Stock symbol (e.g. AAPL).",
    )
    p_fetch.set_defaults(func=cmd_fetch)

    return parser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_tickers(args: argparse.Namespace) -> list[str]:
    """Merge positional tickers and --file tickers into one list."""
    tickers = list(args.tickers or [])
    if args.file:
        with open(args.file) as fh:
            tickers += [line.strip() for line in fh if line.strip()]
    if not tickers:
        print("Error: provide at least one ticker or use --file.", file=sys.stderr)
        sys.exit(1)
    return tickers


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
