"""Scan service: runs discovery + full research over candidates.

Used by the dashboard, the API and the scheduler. Every run is real: the
summary reports per-symbol agent statuses and failures are never hidden.
"""
from __future__ import annotations

from datetime import datetime, timezone

from agents import stock_scout
from agents.base import run_recorded
from engine.orchestrator import research_company


def run_scan(
    index: str = "NIFTY 50",
    limit: int = 50,
    custom_symbols: list[tuple[str, str]] | None = None,
    generate_reports: bool = False,
    on_progress=None,
) -> dict:
    """Discover candidates, then run full research per symbol.

    generate_reports defaults off for 50-stock scans (HTML/CSV/JSON per stock);
    individual company research always generates reports.
    """
    started = datetime.now(timezone.utc)

    scout_result = run_recorded(
        "stock_scout",
        lambda: stock_scout.discover(index=index, limit=limit, custom_symbols=custom_symbols),
        input_summary=f"index={index} limit={limit} custom={bool(custom_symbols)}",
        required_keys=["candidates"],
    )
    if scout_result.status == "failed":
        return {
            "status": "failed",
            "stage": "discovery",
            "error": scout_result.error,
            "started_at": str(started),
        }

    candidates = scout_result.data["candidates"][:limit]
    # Discovery success counts toward source reliability only; it is never
    # treated as cross-source financial consistency (that needs same-company,
    # same-period value comparisons, which free sources cannot supply).
    sources_ok = {
        "nse_archives": scout_result.status in {"success", "partial"} and not custom_symbols,
    }
    results = []
    for position, candidate in enumerate(candidates, start=1):
        if on_progress:
            on_progress(position, len(candidates), candidate["symbol"])
        try:
            outcome = research_company(
                candidate["symbol"], candidate.get("exchange", "NSE"),
                generate_report=generate_reports, sources_ok=sources_ok,
            )
        except Exception as exc:
            outcome = {
                "symbol": candidate["symbol"],
                "exchange": candidate.get("exchange", "NSE"),
                "status": "failed",
                "error": str(exc),
            }
        results.append(outcome)

    succeeded = [r for r in results if r["status"] != "failed"]
    failed = [r for r in results if r["status"] == "failed"]
    return {
        "status": "success" if not failed else ("partial" if succeeded else "failed"),
        "discovered": len(candidates),
        "researched": len(succeeded),
        "failed_symbols": [r["symbol"] for r in failed],
        "results": results,
        "scout_status": scout_result.status,
        "scout_missing": scout_result.missing,
        "started_at": str(started),
        "finished_at": str(datetime.now(timezone.utc)),
    }
