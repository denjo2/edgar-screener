"""
HTTP client for the SEC EDGAR API.

All network calls live here. Nothing else in the project imports `requests`
directly — route through EdgarClient so rate limiting, headers, and timeouts
are applied consistently.

Usage:
    client = EdgarClient()
    cik = client.get_cik("AAPL")
    facts = client.get_company_facts(cik)
    text  = client.get_10k_text(cik)
"""

import time
from typing import Optional

import requests

from config import (
    SEC_HEADERS,
    SEC_RATE_DELAY_SECONDS,
    SEC_API_TIMEOUT_DEFAULT,
    SEC_API_TIMEOUT_FILING,
)


class EdgarError(Exception):
    """Raised when an EDGAR API call fails with a non-200 status."""


class EdgarClient:
    def __init__(
        self,
        headers: dict = SEC_HEADERS,
        rate_delay: float = SEC_RATE_DELAY_SECONDS,
    ) -> None:
        self._headers = headers
        self._rate_delay = rate_delay

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_cik(self, ticker: str) -> Optional[str]:
        """Return zero-padded 10-digit CIK for ticker, or None if not found."""
        data = self._get_json("https://www.sec.gov/files/company_tickers.json")
        for entry in data.values():
            if entry["ticker"].upper() == ticker.upper():
                return str(entry["cik_str"]).zfill(10)
        return None

    def get_company_facts(self, cik: str) -> Optional[dict]:
        """
        Return the full XBRL CompanyFacts JSON for a CIK, or None on 404.
        This is the primary data source for financial metrics.
        """
        url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
        return self._get_json_or_none(url)

    def get_submissions(self, cik: str) -> Optional[dict]:
        """Return the submissions JSON (filing index) for a CIK."""
        url = f"https://data.sec.gov/submissions/CIK{cik}.json"
        return self._get_json_or_none(url)

    def get_10k_text(self, cik: str) -> Optional[str]:
        """
        Fetch the HTML/text of the most recent 10-K primary document.
        Returns None if no 10-K is found in the filing index.
        """
        submissions = self.get_submissions(cik)
        if not submissions:
            return None

        recent = submissions.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        accessions = recent.get("accessionNumber", [])
        primary_docs = recent.get("primaryDocument", [])

        for i, form in enumerate(forms):
            if form == "10-K":
                accession = accessions[i].replace("-", "")
                doc = primary_docs[i]
                cik_int = cik.lstrip("0")
                url = (
                    f"https://www.sec.gov/Archives/edgar/data"
                    f"/{cik_int}/{accession}/{doc}"
                )
                resp = self._get(url, timeout=SEC_API_TIMEOUT_FILING)
                return resp.text

        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get(self, url: str, timeout: int = SEC_API_TIMEOUT_DEFAULT) -> requests.Response:
        resp = requests.get(url, headers=self._headers, timeout=timeout)
        time.sleep(self._rate_delay)
        return resp

    def _get_json(self, url: str) -> dict:
        resp = self._get(url)
        resp.raise_for_status()
        return resp.json()

    def _get_json_or_none(self, url: str) -> Optional[dict]:
        resp = self._get(url)
        if resp.status_code == 200:
            return resp.json()
        return None
