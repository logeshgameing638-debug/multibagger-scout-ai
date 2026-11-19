"""NSE public-file connector.

Only documented, long-stable public CSV files published by NSE on its
archives host are used (index constituents and the listed-equity master).
No scraping of restricted endpoints, no bypass of access controls: if NSE
throttles or blocks the request, the failure is recorded and reported.
"""
from __future__ import annotations

import csv
import io

import requests

from config import get_settings
from .base import BaseConnector, ConnectorResult

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; MultibaggerScoutAI/1.0; research tool)",
    "Accept": "text/csv,*/*",
}

# Public CSV files long published on NSE's archives host.
INDEX_CONSTITUENT_FILES = {
    "NIFTY 50": "https://archives.nseindia.com/content/indices/ind_nifty50list.csv",
    "NIFTY NEXT 50": "https://archives.nseindia.com/content/indices/ind_niftynext50list.csv",
    "NIFTY 100": "https://archives.nseindia.com/content/indices/ind_nifty100list.csv",
    "NIFTY 500": "https://archives.nseindia.com/content/indices/ind_nifty500list.csv",
}
EQUITY_MASTER_URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"


class NSEConnector(BaseConnector):
    name = "nse_archives"
    type = "listings"
    base_url = "https://archives.nseindia.com"

    def _fetch_csv(self, url: str) -> list[dict]:
        response = self._request_with_retry(
            lambda: requests.get(
                url, headers=HEADERS, timeout=get_settings().http_timeout_seconds
            )
        )
        response.raise_for_status()
        text = response.text
        if "<html" in text[:500].lower():
            raise ValueError("provider returned HTML instead of CSV (possible block page)")
        # NSE CSV headers carry leading spaces (" SERIES", " ISIN NUMBER");
        # strip them so downstream lookups use clean names.
        reader = csv.DictReader(io.StringIO(text))
        return [
            {(key or "").strip(): value for key, value in row.items()}
            for row in reader
        ]

    def get_index_constituents(self, index_name: str = "NIFTY 50") -> ConnectorResult:
        url = INDEX_CONSTITUENT_FILES.get(index_name.upper())
        if url is None:
            return ConnectorResult(
                ok=False, source=self.name,
                error=f"unknown index '{index_name}'. Available: {sorted(INDEX_CONSTITUENT_FILES)}",
            )
        try:
            rows = self._fetch_csv(url)
            companies = [
                {
                    "symbol": (row.get("Symbol") or "").strip(),
                    "name": (row.get("Company Name") or "").strip(),
                    "industry": (row.get("Industry") or "").strip(),
                    "exchange": "NSE",
                    "index": index_name,
                }
                for row in rows
                if row.get("Symbol")
            ]
            self.record_health(True)
            return ConnectorResult(ok=True, source=self.name, data=companies)
        except Exception as exc:
            self.record_health(False, str(exc))
            return ConnectorResult(ok=False, source=self.name, error=str(exc))

    def get_equity_master(self) -> ConnectorResult:
        """Full NSE listed-equity master (EQUITY_L.csv)."""
        try:
            rows = self._fetch_csv(EQUITY_MASTER_URL)
            companies = [
                {
                    "symbol": (row.get("SYMBOL") or "").strip(),
                    "name": (row.get("NAME OF COMPANY") or "").strip(),
                    "series": (row.get("SERIES") or "").strip(),
                    "listing_date": (row.get("DATE OF LISTING") or "").strip(),
                    "isin": (row.get("ISIN NUMBER") or "").strip(),
                    "exchange": "NSE",
                }
                for row in rows
                if row.get("SYMBOL")
            ]
            self.record_health(True)
            return ConnectorResult(ok=True, source=self.name, data=companies)
        except Exception as exc:
            self.record_health(False, str(exc))
            return ConnectorResult(ok=False, source=self.name, error=str(exc))

    def health_check(self) -> ConnectorResult:
        result = self.get_index_constituents("NIFTY 50")
        self.record_health(result.ok, result.error)
        return result
