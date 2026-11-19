"""Refresh the committed BSE universe from the latest BSE equity bhavcopy.

The new-format BSE bhavcopy carries alpha ticker symbols (TckrSymb), which
resolve on Yahoo Finance as <symbol>.BO (numeric scrip codes do not). The
extract keeps one row per tradable equity symbol with its ISIN and the
session date it came from, so the rotation can cover BSE stocks with
exchange-aware snapshots. Run before scripts/daily_update.py in the
scheduled workflow; the workflow commits the CSV when it changed.

No paid services: the bhavcopy is a public BSE download.
"""

from __future__ import annotations

import csv
import io
import sys
from datetime import date, timedelta
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "universe_bse.csv"
URL_TMPL = "https://www.bseindia.com/download/Bhavcopy/Equity/BhavCopy_BSE_CM_0_0_0_{ymd}_F_0000.CSV"
HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
LOOKBACK_DAYS = 10  # weekends/holidays: walk back to the latest trading session


def fetch_latest_bhavcopy(today: date | None = None) -> tuple[str, str] | None:
    """Return (csv_text, session_date YYYY-MM-DD) for the latest session."""
    today = today or date.today()
    for back in range(LOOKBACK_DAYS):
        day = today - timedelta(days=back)
        url = URL_TMPL.format(ymd=day.strftime("%Y%m%d"))
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
        except requests.RequestException:
            continue
        if resp.ok and "TckrSymb" in resp.text[:2000]:
            return resp.text, day.isoformat()
    return None


def parse_bhavcopy(csv_text: str) -> list[dict]:
    """One row per equity symbol: symbol, name, isin, session_date, series."""
    rows: list[dict] = []
    seen: set[str] = set()
    for row in csv.DictReader(io.StringIO(csv_text)):
        symbol = (row.get("TckrSymb") or "").strip().upper()
        series = (row.get("SctySrs") or "").strip().upper()
        if not symbol or symbol in seen:
            continue
        if series and series not in ("EQ", "BE", "A", "B"):  # equity groups only
            continue
        seen.add(symbol)
        rows.append({
            "symbol": symbol,
            "name": (row.get("FinInstrmNm") or symbol).strip(),
            "isin": (row.get("ISIN") or "").strip(),
            "exchange": "BSE",
            "series": series,
            "session_date": (row.get("TradDt") or "").strip(),
        })
    return rows


def write_universe(rows: list[dict], path: Path = OUT) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["symbol", "name", "isin",
                                                    "exchange", "series", "session_date"])
        writer.writeheader()
        writer.writerows(rows)
    return path


def main() -> int:
    found = fetch_latest_bhavcopy()
    if found is None:
        print("No BSE bhavcopy found in the lookback window; keeping the committed universe.")
        return 0  # not a failure: the committed CSV stays in use
    csv_text, session = found
    rows = parse_bhavcopy(csv_text)
    if not rows:
        print("Bhavcopy parsed to zero rows; keeping the committed universe.")
        return 0
    path = write_universe(rows)
    print(f"Wrote {len(rows)} BSE equity symbols from session {session} to {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
