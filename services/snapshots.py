"""Read the committed per-stock JSON snapshots produced by the hosted
rotation updater (scripts/daily_update.py via GitHub Actions).

The hosted app restarts wipe its SQLite database, so these snapshots are the
durable record on the hosted site. Every stock carries its own data date;
the UI must always show that date instead of implying one common freshness.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_DIR = ROOT / "data" / "snapshots"
STATE_FILE = ROOT / "data" / "rotation_state.json"


def load_snapshots(directory: Path = SNAPSHOT_DIR) -> dict[str, dict]:
    """symbol -> snapshot dict. Empty when no rotation run has committed yet."""
    snapshots: dict[str, dict] = {}
    if not directory.exists():
        return snapshots
    for path in sorted(directory.glob("*.json")):
        try:
            payload = json.loads(path.read_text())
        except (ValueError, OSError):
            continue
        symbol = payload.get("symbol") or path.stem
        snapshots[symbol] = payload
    return snapshots


def rotation_state(path: Path = STATE_FILE) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (ValueError, OSError):
        return None


def coverage_summary(snapshots: dict[str, dict] | None = None,
                     state: dict | None = None) -> dict | None:
    """Coverage stats for the UI. None when nothing has been committed yet."""
    snapshots = load_snapshots() if snapshots is None else snapshots
    state = rotation_state() if state is None else state
    if not snapshots and not state:
        return None
    dates = [s.get("updated_at") for s in snapshots.values() if s.get("updated_at")]
    complete = sum(1 for s in snapshots.values() if s.get("status") == "complete")
    partial = sum(1 for s in snapshots.values() if s.get("status") == "partial")
    unavailable = sum(1 for s in snapshots.values() if s.get("status") == "unavailable")
    system_error = sum(1 for s in snapshots.values() if s.get("status") == "system_error")
    universe_size = (state or {}).get("universe_size") or 2404
    return {
        "stocks_with_data": len(snapshots),
        "universe_size": universe_size,
        "complete": complete,
        "partial": partial,
        "unavailable": unavailable,
        "system_error": system_error,
        "oldest_data": min(dates) if dates else None,
        "newest_data": max(dates) if dates else None,
        "last_run_at": (state or {}).get("last_run_at"),
        "cycle_started_at": (state or {}).get("cycle_started_at"),
        "coverage_pct": round(100 * len(snapshots) / universe_size, 1) if universe_size else 0.0,
    }


def get_snapshot(symbol: str, exchange: str = "NSE") -> dict | None:
    """Single-stock lookup used as a fallback when the local DB has no score."""
    return load_snapshots().get(symbol.strip().upper())


AUTOMATION_FEED_FILE = ROOT / "data" / "automation" / "alerts_feed.json"


def load_automation_feed(path: Path = AUTOMATION_FEED_FILE) -> dict | None:
    """The committed market-data-only alert feed from scheduled GitHub Actions
    runs (scripts/automation_alerts.py). None when no run has committed yet.
    Contains no watchlists, holdings, orders or user activity."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (ValueError, OSError):
        return None
