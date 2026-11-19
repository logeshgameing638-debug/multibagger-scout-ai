"""Hosted daily rotation updater (GitHub Actions).

Runs one bounded batch of the all-NSE universe on a schedule, writing one
JSON snapshot per stock into data/snapshots/ plus data/rotation_state.json.
Re-runnable and resumable: the cursor in rotation_state.json decides which
stocks are next; after the last stock the cursor wraps and a new cycle starts.

Honest limits, by design:
- This is a ROTATION, not a full-market daily scan. On the free GitHub
  Actions quota a full 2,400-stock scan every day is not feasible, so every
  stock carries its own "data as of" date and the app shows coverage.
- A stock that fails becomes "unavailable" with the error preserved; it is
  retried on the next cycle, not hammered within the run.
- The script stops starting new stocks once the time budget is spent, so the
  workflow always finishes inside the job timeout.
"""

from __future__ import annotations

import csv
import json
import os
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
UNIVERSE_GLOB = "universe_nse_part*.csv"
UNIVERSE_CSV = ROOT / "data" / "universe_nse.csv"
SNAPSHOT_DIR = ROOT / "data" / "snapshots"
STATE_FILE = ROOT / "data" / "rotation_state.json"

IST = timezone(timedelta(hours=5, minutes=30))

DEFAULT_BATCH_SIZE = 150  # measured ~3.4 s/stock in CI; 150 fits the 16-min budget with headroom
DEFAULT_TIME_BUDGET_MINUTES = 16
PER_STOCK_SLEEP_SECONDS = 0.5


def load_universe(path: Path | None = None) -> list[dict]:
    """Read the committed NSE universe list (symbol, name, isin).

    The list is committed as data/universe_nse_part1..3.csv (kept small so it
    can be maintained through the GitHub web UI); a single combined
    universe_nse.csv or an explicit path also works."""
    if path is None:
        parts = sorted((ROOT / "data").glob(UNIVERSE_GLOB))
        paths = parts if parts else [UNIVERSE_CSV]
    else:
        paths = [path]
    rows: list[dict] = []
    seen: set[str] = set()
    for one in paths:
        if not one.exists():
            continue
        with open(one, newline="") as handle:
            for row in csv.DictReader(handle):
                symbol = (row.get("symbol") or "").strip().upper()
                if symbol and symbol not in seen:
                    seen.add(symbol)
                    rows.append(row)
    return rows


def load_state(path: Path | None = None) -> dict:
    path = path or STATE_FILE
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (ValueError, OSError):
            pass
    return {"cursor": 0, "cycle_started_at": None, "run_count": 0}


def pick_batch(universe: list[dict], state: dict, batch_size: int) -> tuple[list[dict], dict]:
    """Pick the next batch after the cursor, wrapping at the end of the list."""
    if not universe:
        return [], state
    state = dict(state)
    cursor = int(state.get("cursor", 0)) % len(universe)
    if cursor == 0:
        # first run or wrapped around: a fresh cycle begins
        state["cycle_started_at"] = _now_ist()
    batch = universe[cursor:cursor + batch_size]
    state["cursor"] = (cursor + len(batch)) % len(universe)
    return batch, state


def _now_ist() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M IST")


def write_snapshot(symbol: str, payload: dict, directory: Path | None = None) -> Path:
    directory = directory or SNAPSHOT_DIR
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{symbol}.json"
    target.write_text(json.dumps(payload, indent=2, default=str))
    return target


def research_one(symbol: str) -> dict:
    """Run the real research pipeline for one stock and shape the snapshot.

    Uses the same engine as the app; the CI database is disposable and only
    the JSON snapshot is committed back."""
    from database import session_scope
    from database.models import Company, ResearchScore
    from engine.orchestrator import research_company
    from sqlalchemy import select

    outcome = research_company(symbol, "NSE", generate_report=False)
    snapshot = {
        "symbol": symbol,
        "exchange": "NSE",
        "updated_at": _now_ist(),
        "status": "complete" if outcome.get("status") == "success" else "partial",
        "agent_statuses": outcome.get("agent_statuses", {}),
    }
    with session_scope() as session:
        company = session.scalar(
            select(Company).where(Company.symbol == symbol, Company.exchange == "NSE")
        )
        if company is not None:
            snapshot["name"] = company.name
            row = session.scalar(
                select(ResearchScore)
                .where(ResearchScore.company_id == company.id)
                .order_by(ResearchScore.id.desc())
                .limit(1)
            )
            if row is not None:
                snapshot["scores"] = {
                    "fundamental": row.fundamental_score,
                    "technical": row.technical_score,
                    "data_confidence": row.data_confidence,
                    "risk": row.risk_score,
                    "long_term": row.long_term_score,
                    "short_term": row.short_term_score,
                    "balanced": row.balanced_score,
                }
                snapshot["classification"] = row.classification
                try:
                    snapshot["explanation"] = json.loads(row.explanation_json or "{}")
                except ValueError:
                    snapshot["explanation"] = {}
            # Structured daily technicals for the automation alert feed
            from database.models import AgentOutput, AgentRun

            tech = session.execute(
                select(AgentOutput)
                .join(AgentRun, AgentRun.id == AgentOutput.run_id)
                .where(AgentRun.agent_name == "technical_analysis",
                       AgentOutput.company_id == company.id)
                .order_by(AgentOutput.created_at.desc())
                .limit(1)
            ).scalar_one_or_none()
            if tech is not None:
                try:
                    daily = json.loads(tech.output_json)["data"]["daily"]
                    snapshot["technical_daily"] = {
                        key: daily.get(key)
                        for key in ("rsi_14", "breakout", "breakdown",
                                    "support", "resistance", "trend")
                        if daily.get(key) is not None
                    }
                except (KeyError, ValueError, TypeError):
                    pass
    return snapshot


def run_batch(batch_size: int = DEFAULT_BATCH_SIZE,
              time_budget_minutes: float = DEFAULT_TIME_BUDGET_MINUTES,
              sleep_seconds: float = PER_STOCK_SLEEP_SECONDS,
              researcher=research_one) -> dict:
    """Process one rotation batch. Returns a summary dict."""
    from database import init_db

    init_db()  # fresh CI checkouts have no database file yet; idempotent
    universe = load_universe()
    state = load_state()
    batch, state = pick_batch(universe, state, batch_size)
    started = time.monotonic()
    budget_seconds = time_budget_minutes * 60

    complete = partial = unavailable = system_error = skipped_budget = 0
    processed: list[str] = []
    for row in batch:
        if time.monotonic() - started > budget_seconds:
            skipped_budget += len(batch) - len(processed)
            break
        symbol = row["symbol"].strip().upper()
        try:
            snapshot = researcher(symbol)
            status = snapshot.get("status", "partial")
        except Exception as exc:  # never let one stock kill the batch
            snapshot = {
                "symbol": symbol,
                "exchange": "NSE",
                "name": row.get("name"),
                "updated_at": _now_ist(),
                # our own failure, not company data being unavailable
                "status": "system_error",
                "error": f"{type(exc).__name__}: {exc}"[:300],
            }
            status = "system_error"
        write_snapshot(symbol, snapshot)
        processed.append(symbol)
        complete += status == "complete"
        partial += status == "partial"
        unavailable += status == "unavailable"
        system_error += status == "system_error"
        if sleep_seconds:
            time.sleep(sleep_seconds)

    state["run_count"] = int(state.get("run_count", 0)) + 1
    state["last_run_at"] = _now_ist()
    state["last_run"] = {
        "attempted": len(processed),
        "complete": complete,
        "partial": partial,
        "unavailable": unavailable,
        "system_error": system_error,
        "skipped_time_budget": skipped_budget,
        "minutes": round((time.monotonic() - started) / 60, 1),
    }
    state["universe_size"] = len(universe)
    STATE_FILE.write_text(json.dumps(state, indent=2))
    return state


def main() -> None:
    batch_size = int(os.environ.get("MB_BATCH_SIZE", DEFAULT_BATCH_SIZE))
    budget = float(os.environ.get("MB_MAX_MINUTES", DEFAULT_TIME_BUDGET_MINUTES))
    state = run_batch(batch_size=batch_size, time_budget_minutes=budget)
    last = state["last_run"]
    print(
        f"Rotation run done: {last['attempted']} stocks "
        f"({last['complete']} complete, {last['partial']} partial, "
        f"{last['unavailable']} unavailable) in {last['minutes']} min. "
        f"Cursor {state['cursor']}/{state['universe_size']}."
    )


if __name__ == "__main__":
    main()
