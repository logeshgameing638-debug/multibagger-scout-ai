"""Scheduled narrative research reports for top-ranked candidates (GitHub Actions).

After the rotation batch and ranking feed, re-runs the full research pipeline
WITH report generation for the current top K candidates, and commits the
report JSON exports to data/automation/reports/<SYMBOL>.json. Market-derived
research only - no watchlists, holdings, orders or user activity.

Reports carry their own generated_at and the underlying data dates. Bounded:
K candidates per run, re-researched fresh each run, so reports never go
stale while remaining inside the job's time budget.
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(ROOT))

RANKING_FEED = ROOT / "data" / "automation" / "ranking_feed.json"
REPORTS_DIR = ROOT / "data" / "automation" / "reports"

IST = timezone(timedelta(hours=5, minutes=30))
TOP_K = 10


def _now_ist() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M IST")


def _load_json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def generate_top_reports(top_k: int = TOP_K,
                         ranking_feed: Path = RANKING_FEED,
                         reports_dir: Path = REPORTS_DIR) -> dict:
    """Re-research the top K ranked candidates with report generation.

    Returns a manifest of the reports committed this run."""
    from database import init_db
    from engine.orchestrator import research_company

    feed = _load_json(ranking_feed, {})
    top = feed.get("top", [])[:top_k]
    if not top:
        return {"generated_at": _now_ist(), "reports": [], "skipped": "no ranked candidates"}

    init_db()  # idempotent on fresh CI checkouts
    reports_dir.mkdir(parents=True, exist_ok=True)
    manifest = {"generated_at": _now_ist(), "reports": []}
    for row in top:
        symbol = row.get("symbol")
        exchange = row.get("exchange", "NSE") or "NSE"
        if not symbol:
            continue
        try:
            outcome = research_company(symbol, exchange, generate_report=True)
            json_path = (outcome.get("reports") or {}).get("json")
            if not json_path or not Path(json_path).exists():
                manifest["reports"].append({
                    "symbol": symbol, "status": "report_unavailable",
                    "note": "research ran but no report file was produced",
                })
                continue
            target = reports_dir / f"{exchange}_{symbol}.json"
            shutil.copyfile(json_path, target)
            # stamp honest automation context onto a copy of the report
            payload = _load_json(target, {})
            if isinstance(payload, dict):
                payload.setdefault("automation", {})
                payload["automation"].update({
                    "generated_at": _now_ist(),
                    "source": "scheduled GitHub Actions run",
                    "rotation_data_date": row.get("data_date"),
                })
                target.write_text(json.dumps(payload, indent=2, default=str))
            manifest["reports"].append({
                "symbol": symbol,
                "exchange": exchange,
                "status": outcome.get("status", "partial"),
                "agent_statuses": outcome.get("agent_statuses", {}),
                "file": f"data/automation/reports/{exchange}_{symbol}.json",
            })
        except Exception as exc:  # one candidate must not kill the batch
            manifest["reports"].append({
                "symbol": symbol,
                "status": "system_error",
                "error": f"{type(exc).__name__}: {exc}"[:300],
            })
    (reports_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    return manifest


if __name__ == "__main__":
    result = generate_top_reports()
    print(json.dumps({"generated_at": result["generated_at"],
                      "reports": len(result["reports"])}))
