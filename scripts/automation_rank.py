"""Scheduled automated research ranking (GitHub Actions).

Ranks the committed per-stock research snapshots into a candidate feed so the
Decision floor shows unattended research output: discovery (rotation),
analysis and risk (snapshot scores), ranking and a saved per-run report.
Market-data-only: no watchlists, holdings, orders or user activity.

Committed as data/automation/ranking_feed.json with run timestamps and
per-stock data dates; stocks with missing/failed agents are flagged, not
silently scored. Cadence follows the scheduled rotation (about one batch per
weekday evening IST; runs can be delayed), not continuous monitoring.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_DIR = ROOT / "data" / "snapshots"
STATE_FILE = ROOT / "data" / "rotation_state.json"
FEED_FILE = ROOT / "data" / "automation" / "ranking_feed.json"

IST = timezone(timedelta(hours=5, minutes=30))
TOP_N = 25


def _now_ist() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M IST")


def _load_json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def build_ranking(snapshots: dict[str, dict], state: dict, now: str) -> dict:
    ranked = []
    excluded = 0
    for symbol, snap in snapshots.items():
        status = snap.get("status", "partial")
        scores = snap.get("scores") or {}
        balanced = scores.get("balanced")
        if status in ("unavailable", "system_error") or balanced is None:
            excluded += 1
            continue
        missing_agents = [name for name, st in (snap.get("agent_statuses") or {}).items()
                          if st != "success"]
        classification = snap.get("classification") or "unclassified"
        verdict = (f"{classification} - balanced {balanced:.1f}, "
                   f"stored risk {scores.get('risk') if scores.get('risk') is not None else 'n/a'}"
                   + (", partial data" if status == "partial" else ""))
        ranked.append({
            "symbol": symbol,
            "exchange": snap.get("exchange", "NSE"),
            "verdict": verdict,
            "name": snap.get("name"),
            "balanced": balanced,
            "long_term": scores.get("long_term"),
            "short_term": scores.get("short_term"),
            "risk": scores.get("risk"),
            "data_confidence": scores.get("data_confidence"),
            "classification": snap.get("classification"),
            "status": status,
            "data_date": snap.get("updated_at"),
            "missing_agents": missing_agents,
        })
    ranked.sort(key=lambda r: (-(r["balanced"] if isinstance(r["balanced"], (int, float)) else -1),
                               r["symbol"]))
    for i, row in enumerate(ranked, 1):
        row["rank"] = i
    return {
        "generated_at": now,
        "rotation_last_run_at": state.get("last_run_at"),
        "cycle_started_at": state.get("cycle_started_at"),
        "universe_size": state.get("universe_size"),
        "ranked_count": len(ranked),
        "excluded_count": excluded,
        "top": ranked[:TOP_N],
    }


def run(snapshot_dir: Path = SNAPSHOT_DIR, state_file: Path = STATE_FILE,
        feed_file: Path = FEED_FILE) -> dict:
    snapshots: dict[str, dict] = {}
    if snapshot_dir.exists():
        for path in sorted(snapshot_dir.glob("*.json")):
            payload = _load_json(path, None)
            if isinstance(payload, dict) and payload.get("symbol"):
                snapshots[payload["symbol"]] = payload
    state = _load_json(state_file, {})
    feed = build_ranking(snapshots, state, _now_ist())
    feed_file.parent.mkdir(parents=True, exist_ok=True)
    feed_file.write_text(json.dumps(feed, indent=2, default=str))
    return feed


if __name__ == "__main__":
    result = run()
    print(json.dumps({k: result[k] for k in
                      ("generated_at", "ranked_count", "excluded_count")}))
