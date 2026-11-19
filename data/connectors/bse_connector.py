"""BSE connector.

BSE does not publish a stable documented public listing API comparable to
NSE's archives CSVs. This connector therefore supports two honest modes:

1. Configurable scrip-master CSV download (BSE_EQUITY_MASTER_URL env var);
   when unset or failing, the failure is recorded, never hidden.
2. Yahoo Finance .BO symbols for prices/fundamentals of BSE-listed scrips.

It never invents listings: discovery output always comes from a fetched file.
"""
from __future__ import annotations

import csv
import io
import os

import requests

from config import get_settings
from .base import BaseConnector, ConnectorResult

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; MultibaggerScoutAI/1.0; research tool)",
    "Accept": "text/csv,*/*",
}

# BSE publishes an equity scrip master CSV from its site. The exact path has
# changed over time, so it is configurable; when it fails, health shows it.
DEFAULT_BSE_EQUITY_MASTER_URL = "https://www.bseindia.com/download/Equity.csv"


class BSEConnector(BaseConnector):
    name = "bse_site"
    type = "listings"
    base_url = "https://www.bseindia.com"

    @property
    def equity_master_url(self) -> str:
        return os.environ.get("BSE_EQUITY_MASTER_URL", DEFAULT_BSE_EQUITY_MASTER_URL)

    def get_equity_master(self) -> ConnectorResult:
        try:
            response = self._request_with_retry(
                lambda: requests.get(
                    self.equity_master_url,
                    headers=HEADERS,
                    timeout=get_settings().http_timeout_seconds,
                )
            )
            response.raise_for_status()
            text = response.text
            if "<html" in text[:500].lower():
                raise ValueError("BSE returned HTML instead of CSV (possible block page)")
            rows = list(csv.DictReader(io.StringIO(text)))
            companies = []
            for row in rows:
                normalised = {str(k).strip().upper(): (v or "").strip() for k, v in row.items()}
                code = normalised.get("SCRIP CODE") or normalised.get("SECURITY CODE") or ""
                name = (
                    normalised.get("SCRIP NAME")
                    or normalised.get("SECURITY NAME")
                    or normalised.get("ISSUER NAME")
                    or ""
                )
                if code:
                    companies.append(
                        {"symbol": code, "scrip_code": code, "name": name, "exchange": "BSE"}
                    )
            if not companies:
                raise ValueError("BSE CSV parsed but no scrip rows found (format changed?)")
            self.record_health(True)
            return ConnectorResult(ok=True, source=self.name, data=companies)
        except Exception as exc:
            self.record_health(False, str(exc))
            return ConnectorResult(
                ok=False,
                source=self.name,
                error=(
                    f"BSE scrip master unavailable: {exc}. "
                    "Set BSE_EQUITY_MASTER_URL to a current CSV export from bseindia.com, "
                    "or add BSE symbols manually (prices via Yahoo Finance .BO)."
                ),
            )

    def health_check(self) -> ConnectorResult:
        result = self.get_equity_master()
        self.record_health(result.ok, result.error)
        return result
