"""Watchlist service: named lists, items, and monitoring evaluation."""
from __future__ import annotations

from sqlalchemy import select

from database.connection import session_scope
from database.models import Alert, Company, ResearchScore, Watchlist, WatchlistItem

MULTIBAGGER_LIST = "Multibagger Watchlist"


def get_or_create_watchlist(name: str = MULTIBAGGER_LIST, kind: str = "multibagger") -> int:
    with session_scope() as session:
        wl = session.scalar(select(Watchlist).where(Watchlist.name == name))
        if wl is None:
            wl = Watchlist(name=name, kind=kind)
            session.add(wl)
            session.flush()
        return wl.id


def add_symbol(symbol: str, exchange: str = "NSE", note: str = "", list_name: str = MULTIBAGGER_LIST) -> dict:
    list_id = get_or_create_watchlist(list_name)
    with session_scope() as session:
        company = session.scalar(
            select(Company).where(Company.symbol == symbol.upper(), Company.exchange == exchange.upper())
        )
        if company is None:
            return {"ok": False, "error": f"{symbol} ({exchange}) not researched yet - run research first"}
        existing = session.scalar(
            select(WatchlistItem).where(
                WatchlistItem.watchlist_id == list_id, WatchlistItem.company_id == company.id
            )
        )
        if existing:
            return {"ok": True, "already_present": True}
        session.add(WatchlistItem(watchlist_id=list_id, company_id=company.id, note=note))
        return {"ok": True, "already_present": False}


def remove_symbol(symbol: str, exchange: str = "NSE", list_name: str = MULTIBAGGER_LIST) -> dict:
    with session_scope() as session:
        wl = session.scalar(select(Watchlist).where(Watchlist.name == list_name))
        if wl is None:
            return {"ok": False, "error": "watchlist not found"}
        company = session.scalar(
            select(Company).where(Company.symbol == symbol.upper(), Company.exchange == exchange.upper())
        )
        if company is None:
            return {"ok": False, "error": "company not found"}
        item = session.scalar(
            select(WatchlistItem).where(
                WatchlistItem.watchlist_id == wl.id, WatchlistItem.company_id == company.id
            )
        )
        if item:
            session.delete(item)
        return {"ok": True}


def list_items(list_name: str = MULTIBAGGER_LIST) -> list[dict]:
    with session_scope() as session:
        wl = session.scalar(select(Watchlist).where(Watchlist.name == list_name))
        if wl is None:
            return []
        rows = session.execute(
            select(WatchlistItem, Company)
            .join(Company, Company.id == WatchlistItem.company_id)
            .where(WatchlistItem.watchlist_id == wl.id)
        ).all()
        output = []
        for item, company in rows:
            latest_score = session.scalar(
                select(ResearchScore)
                .where(ResearchScore.company_id == company.id)
                .order_by(ResearchScore.created_at.desc())
                .limit(1)
            )
            output.append(
                {
                    "symbol": company.symbol,
                    "exchange": company.exchange,
                    "name": company.name,
                    "note": item.note,
                    "added_at": str(item.added_at),
                    "balanced_score": latest_score.balanced_score if latest_score else None,
                    "risk_classification": None,
                    "labels": latest_score.classification if latest_score else None,
                }
            )
        return output


def auto_update_from_scores() -> int:
    """Add companies labelled potential_multibagger_hypothesis to the
    multibagger watchlist. Returns number newly added."""
    added = 0
    with session_scope() as session:
        latest_ids = session.execute(
            select(ResearchScore.company_id, ResearchScore.classification)
            .distinct(ResearchScore.company_id)
            .order_by(ResearchScore.company_id, ResearchScore.created_at.desc())
        ).all()
    seen: set[int] = set()
    for company_id, classification in latest_ids:
        if company_id in seen:
            continue
        seen.add(company_id)
        if classification and "potential_multibagger_hypothesis" in classification:
            with session_scope() as session:
                company = session.get(Company, company_id)
            if company:
                outcome = add_symbol(company.symbol, company.exchange, note="auto: hypothesis label")
                if outcome.get("ok") and not outcome.get("already_present"):
                    added += 1
    return added
