"""Full listing-universe loading and resumable scanning.

Universe sources are official public files: NSE's equity master (EQUITY_L.csv,
EQ series = equities) and BSE's scrip master (configurable URL). Companies on
both exchanges are deduplicated by ISIN: one Company row, one ExchangeSymbol
row per exchange. Scanning is bounded and resumable: research_status lives in
the database, so any run continues where the last stopped, and every company
ends up complete / partial / unavailable - never silently skipped.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

from sqlalchemy import func, select

from data.connectors import default_registry
from database.connection import session_scope
from database.models import Company, ExchangeSymbol


def load_nse_universe() -> dict:
    """Load all NSE EQ-series equities. Returns counts."""
    registry = default_registry()
    result = registry.get("nse_archives").get_equity_master()
    if not result.ok:
        return {"ok": False, "error": result.error}
    added = linked = skipped = 0
    with session_scope() as session:
        for row in result.data:
            if row.get("series") != "EQ":
                skipped += 1
                continue
            symbol, name = row["symbol"], row.get("name") or row["symbol"]
            isin = row.get("isin") or None
            existing = session.scalar(
                select(Company).where(Company.symbol == symbol, Company.exchange == "NSE")
            )
            if existing is None and isin:
                # dedupe: same company already known from another exchange
                twin = session.scalar(select(Company).where(Company.isin == isin))
                if twin is not None:
                    if session.scalar(
                        select(ExchangeSymbol).where(
                            ExchangeSymbol.exchange == "NSE",
                            ExchangeSymbol.symbol == symbol,
                        )
                    ) is None:
                        session.add(ExchangeSymbol(
                            company_id=twin.id, exchange="NSE", symbol=symbol,
                            source="nse_archives",
                        ))
                    linked += 1
                    continue
            if existing is None:
                session.add(Company(
                    symbol=symbol, exchange="NSE", name=name, isin=isin,
                    instrument_type="equity",
                ))
                added += 1
    return {"ok": True, "added": added, "linked_existing": linked, "skipped_non_equity": skipped}


def load_bse_universe() -> dict:
    """Load BSE scrips from the configurable master CSV. Honest failure when
    the master is unavailable."""
    registry = default_registry()
    result = registry.get("bse_site").get_equity_master()
    if not result.ok:
        return {"ok": False, "error": result.error}
    added = 0
    with session_scope() as session:
        for row in result.data:
            code = row["symbol"]
            existing = session.scalar(
                select(Company).where(Company.symbol == code, Company.exchange == "BSE")
            )
            if existing is None:
                session.add(Company(
                    symbol=code, exchange="BSE",
                    name=row.get("name") or code,
                    instrument_type="equity",
                ))
                added += 1
    return {"ok": True, "added": added}


def universe_progress() -> dict:
    with session_scope() as session:
        total = session.scalar(select(func.count(Company.id)).where(Company.is_active.is_(True))) or 0
        by_status = dict(
            session.execute(
                select(Company.research_status, func.count()).group_by(Company.research_status)
            ).all()
        )
    return {"total": total, "by_status": by_status}


def scan_universe(
    exchange: str | None = None,
    batch_size: int = 25,
    sleep_seconds: float = 1.0,
    on_progress=None,
) -> dict:
    """Research the next batch of pending companies. Re-runnable: each call
    picks up where the previous one stopped. Failed-provider symbols become
    'unavailable' with the error preserved, and are retried on later runs only
    after a manual reset (Settings) to avoid hammering providers."""
    from engine.orchestrator import research_company

    with session_scope() as session:
        query = select(Company).where(Company.research_status == "pending")
        if exchange:
            query = query.where(Company.exchange == exchange)
        batch = session.scalars(query.order_by(Company.id).limit(batch_size)).all()
        todo = [(c.id, c.symbol, c.exchange) for c in batch]

    done = partial = failed = 0
    for index, (company_id, symbol, exch) in enumerate(todo, start=1):
        if on_progress:
            on_progress(index, len(todo), symbol)
        try:
            outcome = research_company(symbol, exch, generate_report=False)
            status = "complete" if outcome["status"] == "success" else "partial"
            done += status == "complete"
            partial += status == "partial"
        except Exception:
            status = "unavailable"
            failed += 1
        with session_scope() as session:
            company = session.get(Company, company_id)
            company.research_status = status
            company.researched_at = datetime.now(timezone.utc)
        if sleep_seconds:
            time.sleep(sleep_seconds)
    progress = universe_progress()
    return {
        "batch": len(todo), "complete": done, "partial": partial, "failed": failed,
        "progress": progress,
    }
