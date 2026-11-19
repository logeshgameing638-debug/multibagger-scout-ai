"""Rebuild data/automation/cap_sections.json from committed snapshots.

Joins the ranked snapshot scores (same logic as scripts/automation_rank.py)
with the committed AMFI cap-class map (data/amfi_cap_map.json, refreshed
half-yearly from the AMFI average market-capitalization list) and the latest
BSE bhavcopy close prices. Symbols not in the AMFI list are reported as
"unknown_cap" - never guessed. Penny section = close below the penny cutoff.
Runs after automation_rank.py in the scheduled workflow; never fails the run.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import automation_rank  # scripts/automation_rank.py
from update_bse_universe import fetch_latest_bhavcopy

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_DIR = ROOT / "data" / "snapshots"
STATE_FILE = ROOT / "data" / "rotation_state.json"
CAP_MAP_FILE = ROOT / "data" / "amfi_cap_map.json"
OUT = ROOT / "data" / "automation" / "cap_sections.json"
IST = ZoneInfo("Asia/Kolkata")
PENNY_CUTOFF_INR = 10

CAP_LABELS = {
    "Large Cap": "large_cap",
    "Mid Cap": "mid_cap",
    "Small Cap": "small_cap",
}


def bhavcopy_closes() -> tuple[dict[str, dict], str | None]:
    """symbol -> {close, volume, traded_value} from the latest BSE bhavcopy."""
    got = fetch_latest_bhavcopy()
    if not got:
        return {}, None
    csv_text, session = got
    out: dict[str, dict] = {}
    for row in csv.DictReader(io.StringIO(csv_text)):
        sym = (row.get("TckrSymb") or "").strip().upper()
        if not sym:
            continue
        try:
            out[sym] = {
                "close": float(row.get("ClsPric") or 0) or None,
                "volume": int(float(row.get("TtlTradgVol") or 0)),
                "traded_value": float(row.get("TtlTrfVal") or 0),
            }
        except (TypeError, ValueError):
            continue
    return out, session


def main() -> int:
    now = datetime.now(IST).strftime("%Y-%m-%d %H:%M IST")
    snapshots = {}
    for path in sorted(SNAPSHOT_DIR.glob("*.json")):
        payload = automation_rank._load_json(path, None)
        if isinstance(payload, dict) and payload.get("symbol"):
            snapshots[payload["symbol"]] = payload
    state = automation_rank._load_json(STATE_FILE, {})
    automation_rank.TOP_N = 1_000_000  # cap sections need the full ranked list, not the feed's top 25
    feed = automation_rank.build_ranking(snapshots, state, now)
    ranked = feed.get("top", [])
    cap_ref = json.loads(CAP_MAP_FILE.read_text())
    cap_map: dict[str, str] = cap_ref.get("map", {})
    closes, session = bhavcopy_closes()

    sections: dict[str, list] = {"large_cap": [], "mid_cap": [], "small_cap": [], "unknown_cap": []}
    penny = []
    for row in ranked:
        sym = row["symbol"]
        rec = {k: row.get(k) for k in ("rank", "symbol", "exchange", "name", "balanced", "risk",
                                       "data_confidence", "classification", "status", "data_date")}
        bh = closes.get(sym) or {}
        rec["close"] = bh.get("close")
        cls = cap_map.get(sym)
        rec["cap_class"] = cls
        sections[CAP_LABELS.get(cls, "unknown_cap")].append(rec)
        close = bh.get("close")
        if close is not None and close < PENNY_CUTOFF_INR:
            penny.append(rec)

    all_rows = [r for rows in sections.values() for r in rows]
    top50 = sorted(all_rows, key=lambda r: (-(r["balanced"] if isinstance(r["balanced"], (int, float)) else -1), r["symbol"]))[:50]

    out = {
        "generated_at": now,
        "sources": {
            "cap_classification": cap_ref.get("source"),
            "prices": f"BSE official equity bhavcopy close, session {session}" if session else "BSE bhavcopy unavailable this run; close fields kept from prior run where absent",
            "scores": f"committed research snapshots; ranking feed generated {feed.get('generated_at')}",
        },
        "penny_cutoff_inr": PENNY_CUTOFF_INR,
        "ranked_count": len(all_rows),
        "counts": {k: len(v) for k, v in sections.items()} | {"penny": len(penny)},
        "top50": top50,
        "sections": sections,
        "penny": penny,
    }
    OUT.write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps({"written": str(OUT), "counts": out["counts"], "session": session}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
