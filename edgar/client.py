"""
HTTP client for the SEC EDGAR API.
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
    pass


class EdgarClient:
    def __init__(self, headers=SEC_HEADERS, rate_delay=SEC_RATE_DELAY_SECONDS):
        self._headers = headers
        self._rate_delay = rate_delay

    def get_cik(self, ticker):
        data = self._get_json("https://www.sec.gov/files/company_tickers.json")
        for entry in data.values():
            if entry["ticker"].upper() == ticker.upper():
                return str(entry["cik_str"]).zfill(10)
        return None

    def get_company_facts(self, cik):
        url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
        return self._get_json_or_none(url)

    def get_submissions(self, cik):
        url = f"https://data.sec.gov/submissions/CIK{cik}.json"
        return self._get_json_or_none(url)

    def get_10k_text(self, cik):
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
                url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession}/{doc}"
                resp = self._get(url, timeout=SEC_API_TIMEOUT_FILING)
                return resp.text
        return None

    def _get(self, url, timeout=SEC_API_TIMEOUT_DEFAULT):
        resp = requests.get(url, headers=self._headers, timeout=timeout)
        time.sleep(self._rate_delay)
        return resp

    def _get_json(self, url, retries=5):
        for attempt in range(retries):
            resp = self._get(url)
            resp.raise_for_status()
            if resp.text.strip():
                return resp.json()
            wait = 2 ** attempt * 5
            print(f"Empty response from SEC (attempt {attempt+1}/{retries}), retrying in {wait}s...")
            time.sleep(wait)
        raise EdgarError(f"SEC returned empty response after {retries} attempts: {url}")

    def _get_json_or_none(self, url, retries=5):
        for attempt in range(retries):
            resp = self._get(url)
            if resp.status_code == 404:
                return None
            if resp.status_code == 200 and resp.text.strip():
                return resp.json()
            wait = 2 ** attempt * 5
            print(f"Empty/unexpected response from SEC (attempt {attempt+1}/{retries}), retrying in {wait}s...")
            time.sleep(wait)
        return None
