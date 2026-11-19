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
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
    "Accept": "text/csv,*/*",
    "Referer": "https://www.bseindia.com/",
}

# SEBI's common bhavcopy is published daily per exchange; the equity segment
# file lists every active BSE stock (FinInstrmTp=STK) with symbol, ISIN and
# name. Used as the fallback universe source when the scrip-master CSV path
# serves the site's HTML shell instead of data.
BHAVCOPY_URL = ("https://www.bseindia.com/download/Bhavcopy/Equity/"
                "BhavCopy_BSE_CM_0_0_0_{date}_F_0000.CSV")

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
        result = self._master_from_config_url()
        if result.ok:
            return result
        master_error = result.error or "unknown error"
        fallback = self._master_from_bhavcopy()
        if fallback.ok:
            return fallback
        self.record_health(False, f"{master_error} | bhavcopy: {fallback.error}")
        return ConnectorResult(
            ok=False,
            source=self.name,
            error=(
                f"BSE universe unavailable. Scrip master: {master_error}. "
                f"Daily bhavcopy fallback: {fallback.error}. "
                "Set BSE_EQUITY_MASTER_URL to a current CSV export from bseindia.com, "
                "or add BSE symbols manually (prices via Yahoo Finance .BO)."
            ),
        )

    def _master_from_config_url(self) -> ConnectorResult:
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
            return ConnectorResult(ok=False, source=self.name, error=str(exc))

    def _master_from_bhavcopy(self, max_lookback_days: int = 10) -> ConnectorResult:
        """Equity universe from the official daily common bhavcopy."""
        from datetime import datetime, timedelta, timezone

        ist = timezone(timedelta(hours=5, minutes=30))
        today = datetime.now(ist).date()
        last_error = "no trading day found in lookback window"
        for offset in range(0, max_lookback_days + 1):
            day = today - timedelta(days=offset)
            if day.weekday() >= 5:  # weekend: no file exists
                continue
            url = BHAVCOPY_URL.format(date=day.strftime("%Y%m%d"))
            try:
                response = requests.get(
                    url, headers=HEADERS, timeout=get_settings().http_timeout_seconds
                )
                if response.status_code != 200 or "<html" in response.text[:500].lower():
                    last_error = f"{day}: no bhavcopy file (HTTP {response.status_code})"
                    continue
                rows = list(csv.DictReader(io.StringIO(response.text)))
                companies = []
                for row in rows:
                    if (row.get("FinInstrmTp") or "").strip() != "STK":
                        continue
                    symbol = (row.get("TckrSymb") or "").strip()
                    if not symbol:
                        continue
                    companies.append(
                        {
                            "symbol": symbol,
                            "name": (row.get("FinInstrmNm") or "").strip() or symbol,
                            "isin": (row.get("ISIN") or "").strip() or None,
                            "series": (row.get("SctySrs") or "").strip(),
                            "exchange": "BSE",
                        }
                    )
                if not companies:
                    last_error = f"{day}: bhavcopy parsed but no STK rows (format changed?)"
                    continue
                self.record_health(True)
                return ConnectorResult(ok=True, source=self.name, data=companies)
            except Exception as exc:
                last_error = f"{day}: {exc}"
        return ConnectorResult(ok=False, source=self.name, error=last_error)

    def health_check(self) -> ConnectorResult:
        result = self.get_equity_master()
        self.record_health(result.ok, result.error)
        return result
