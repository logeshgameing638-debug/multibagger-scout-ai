"""Rebuild data/automation/etf_sections.json for the curated ETF universe.

NAVs come from the official AMFI NAVAll file (free, daily). Exchange closes
come from the latest BSE equity bhavcopy (free, per trading session), matched
to the curated list in data/etf_universe.json by symbol and cross-checked by
ISIN where the NAVAll line carries one. No paid services. If a source is
unreachable the script exits non-zero WITHOUT touching the committed feed, so
the last good feed stays live; the workflow step is continue-on-error.
"""

from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from update_bse_universe import fetch_latest_bhavcopy

ROOT = Path(__file__).resolve().parent.parent
UNIVERSE_FILE = ROOT / "data" / "etf_universe.json"
OUT = ROOT / "data" / "automation" / "etf_sections.json"
IST = ZoneInfo("Asia/Kolkata")
NAVALL_URL = "https://portal.amfiindia.com/spages/NAVAll.txt"
HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}


def fetch_navall() -> tuple[dict[str, dict], str | None]:
    """ISIN -> {nav, nav_date} from the AMFI NAVAll file."""
    resp = requests.get(NAVALL_URL, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    out: dict[str, dict] = {}
    latest_date: str | None = None
    for line in resp.text.splitlines():
        parts = line.split(";")
        if len(parts) < 6:
            continue
        isin_div = (parts[1] or "").strip()  # ISIN Div Payout/IDCW field
        isin_reinv = (parts[2] or "").strip()
        isin = isin_div or isin_reinv
        if not re.fullmatch(r"INF[A-Z0-9]{9}", isin or ""):
            continue
        try:
            nav = float(parts[-2])  # last two fields are always NAV;date
        except (TypeError, ValueError):
            continue
        nav_date = (parts[-1] or "").strip()
        out[isin] = {"nav": nav, "nav_date": nav_date}
        latest_date = nav_date or latest_date
    return out, latest_date


def main() -> int:
    now = datetime.now(IST).strftime("%Y-%m-%d %H:%M IST")
    universe = json.loads(UNIVERSE_FILE.read_text())["etfs"]
    navs, nav_file_date = fetch_navall()
    got = fetch_latest_bhavcopy()
    if not got:
        raise RuntimeError("BSE bhavcopy unavailable; leaving committed ETF feed untouched")
    csv_text, session = got
    bhav: dict[str, dict] = {}
    for row in csv.DictReader(io.StringIO(csv_text)):
        sym = (row.get("TckrSymb") or "").strip().upper()
        if sym:
            try:
                bhav[sym] = {
                    "close": float(row.get("ClsPric") or 0) or None,
                    "day_volume": int(float(row.get("TtlTradgVol") or 0)),
                    "day_traded_value": float(row.get("TtlTrfVal") or 0),
                    "isin": (row.get("ISIN") or "").strip(),
                }
            except (TypeError, ValueError):
                continue

    etfs = []
    missing = []
    for e in universe:
        sym, isin = e["symbol"], e["isin"]
        nav_rec = navs.get(isin) or {}
        bh = bhav.get(sym) or {}
        if bh.get("isin") and isin and bh["isin"] != isin:
            # symbol/ISIN mismatch between sources: keep both facts, flag it
            mismatch = True
        else:
            mismatch = False
        nav = nav_rec.get("nav")
        close = bh.get("close")
        rec = {
            "symbol": sym,
            "isin": isin,
            "name": e.get("name"),
            "category": e.get("category"),
            "tracks": e.get("tracks"),
            "nav": nav,
            "nav_date": nav_rec.get("nav_date"),
            "close": close,
            "close_session": session if close is not None else None,
            "day_volume": bh.get("day_volume"),
            "day_traded_value": bh.get("day_traded_value"),
            "close_vs_nav_pct": round((close / nav - 1) * 100, 2) if nav and close else None,
        }
        if mismatch:
            rec["source_isin_mismatch"] = bh.get("isin")
        if nav is None or close is None:
            missing.append(sym)
        etfs.append(rec)

    out = {
        "generated_at": now,
        "sources": {
            "nav": f"AMFI NAVAll file, NAVs dated {nav_file_date} ({NAVALL_URL})",
            "prices": f"BSE official equity bhavcopy, session {session}",
        },
        "count": len(etfs),
        "etfs": etfs,
    }
    OUT.write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps({"written": str(OUT), "count": len(etfs), "missing_fields": missing, "session": session}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
