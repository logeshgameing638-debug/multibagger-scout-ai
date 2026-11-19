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

# The hosted app can serve a stale on-disk copy of the committed automation
# feeds when a redeploy does not restart the running process. Reading the
# files from the GitHub contents API instead makes each nightly feed commit
# visible to any fresh session without a manual reboot. Local disk remains
# the fallback (and the only source in tests and offline runs).
import os
import time

GITHUB_REPO = os.environ.get("MSA_GITHUB_REPO", "logeshgameing638-debug/multibagger-scout-ai")
GITHUB_BRANCH = os.environ.get("MSA_GITHUB_BRANCH", "main")
REMOTE_TTL_SECONDS = 900  # 15 min: hourly commits stay fresh, API limits safe
_remote_cache: dict[str, tuple[float, dict | None]] = {}


def _fetch_repo_json(repo_relpath: str) -> dict | None:
    """Fetch one committed JSON file from the GitHub contents API, cached
    in-process for REMOTE_TTL_SECONDS. None on any failure."""
    now = time.time()
    cached = _remote_cache.get(repo_relpath)
    if cached is not None and now - cached[0] < REMOTE_TTL_SECONDS:
        return cached[1]
    value: dict | None = None
    try:
        import requests
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{repo_relpath}"
        resp = requests.get(
            url,
            headers={"Accept": "application/vnd.github.v3.raw"},
            params={"ref": GITHUB_BRANCH},
            timeout=10,
        )
        if resp.ok:
            value = resp.json()
    except Exception:
        value = None
    _remote_cache[repo_relpath] = (now, value)
    return value


def _load_json_local(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (ValueError, OSError):
        return None


def _load_json_fresh(path: Path, repo_relpath: str) -> dict | None:
    """Remote-first for the repo's default committed path, local fallback;
    custom paths (tests) stay local-only."""
    default = (ROOT / repo_relpath).resolve()
    try:
        is_default = path.resolve() == default
    except OSError:
        is_default = False
    if is_default:
        remote = _fetch_repo_json(repo_relpath)
        if isinstance(remote, dict):
            return remote
    return _load_json_local(path)



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
    return _load_json_fresh(path, "data/automation/alerts_feed.json")


RANKING_FEED_FILE = ROOT / "data" / "automation" / "ranking_feed.json"


def load_ranking_feed(path: Path = RANKING_FEED_FILE) -> dict | None:
    """The committed automated research ranking from scheduled runs
    (scripts/automation_rank.py). None when no run has committed yet."""
    return _load_json_fresh(path, "data/automation/ranking_feed.json")


REPORTS_MANIFEST_FILE = ROOT / "data" / "automation" / "reports" / "manifest.json"
REPORTS_DIR = ROOT / "data" / "automation" / "reports"


def load_reports_manifest(path: Path = REPORTS_MANIFEST_FILE) -> dict | None:
    """Manifest of automated narrative research reports from scheduled runs.
    None when no run has committed reports yet."""
    return _load_json_fresh(path, "data/automation/reports/manifest.json")


def load_report(symbol: str, exchange: str = "NSE",
                directory: Path = REPORTS_DIR) -> dict | None:
    """One committed automated research report JSON. None when absent."""
    fname = f"{exchange}_{symbol}.json"
    return _load_json_fresh(directory / fname, f"data/automation/reports/{fname}")
