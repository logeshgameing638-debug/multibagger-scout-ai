"""FastAPI backend. Local-first: binds to 127.0.0.1 by default."""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from sqlalchemy import select

from config import get_settings
from data.connectors import default_registry
from database.connection import init_db, session_scope
from database.models import Alert, Company, DataSource, ResearchScore
from engine.orchestrator import research_company
from services import alerts as alerts_service
from services import scheduler as scheduler_service
from services import watchlist as watchlist_service
from services.scanner import run_scan

from .schemas import (
    CompanyOut,
    JobToggleRequest,
    ResearchRequest,
    ScanRequest,
    ScoreOut,
    WatchlistAddRequest,
)


def create_app() -> FastAPI:
    app = FastAPI(title="Multibagger Scout AI", version="1.0.0")
    init_db()

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "service": "multibagger-scout-ai"}

    @app.get("/companies", response_model=list[CompanyOut])
    def companies() -> list[dict]:
        with session_scope() as session:
            rows = session.scalars(select(Company).order_by(Company.symbol)).all()
            return [
                {
                    "symbol": c.symbol, "exchange": c.exchange, "name": c.name,
                    "sector": c.sector, "industry": c.industry, "market_cap": c.market_cap,
                }
                for c in rows
            ]

    @app.post("/research")
    def research(request: ResearchRequest) -> dict:
        outcome = research_company(request.symbol, request.exchange)
        if outcome["status"] == "failed":
            raise HTTPException(status_code=502, detail=outcome.get("error", "research failed"))
        return outcome

    @app.post("/scan")
    def scan(request: ScanRequest) -> dict:
        custom = None
        if request.custom_symbols:
            custom = []
            for item in request.custom_symbols:
                symbol, _, exchange = item.partition(":")
                custom.append((symbol.strip(), (exchange.strip() or "NSE").upper()))
        return run_scan(index=request.index, limit=request.limit,
                        custom_symbols=custom, generate_reports=request.generate_reports)

    @app.get("/scores", response_model=list[ScoreOut])
    def scores() -> list[dict]:
        with session_scope() as session:
            subq = (
                select(ResearchScore.company_id, ResearchScore.created_at)
                .order_by(ResearchScore.created_at.desc())
            )
            rows = session.execute(
                select(ResearchScore, Company.symbol)
                .join(Company, Company.id == ResearchScore.company_id)
                .order_by(ResearchScore.created_at.desc())
                .limit(200)
            ).all()
            return [
                {
                    "symbol": symbol,
                    "fundamental_score": s.fundamental_score,
                    "technical_score": s.technical_score,
                    "data_confidence": s.data_confidence,
                    "risk_score": s.risk_score,
                    "long_term_score": s.long_term_score,
                    "short_term_score": s.short_term_score,
                    "balanced_score": s.balanced_score,
                    "classification": s.classification,
                    "created_at": str(s.created_at),
                }
                for s, symbol in rows
            ]

    @app.get("/scores/{symbol}")
    def score_history(symbol: str, exchange: str = "NSE") -> list[dict]:
        with session_scope() as session:
            company = session.scalar(
                select(Company).where(Company.symbol == symbol.upper(), Company.exchange == exchange.upper())
            )
            if company is None:
                raise HTTPException(status_code=404, detail="company not found")
            rows = session.scalars(
                select(ResearchScore)
                .where(ResearchScore.company_id == company.id)
                .order_by(ResearchScore.created_at.desc())
            ).all()
            return [
                {"balanced": r.balanced_score, "fundamental": r.fundamental_score,
                 "technical": r.technical_score, "created_at": str(r.created_at)}
                for r in rows
            ]

    @app.get("/alerts")
    def get_alerts(status: str | None = "open") -> list[dict]:
        return alerts_service.list_alerts(status=status)

    @app.post("/alerts/{alert_id}/acknowledge")
    def acknowledge(alert_id: int) -> dict:
        if not alerts_service.acknowledge(alert_id):
            raise HTTPException(status_code=404, detail="alert not found")
        return {"ok": True}

    @app.get("/watchlist")
    def watchlist() -> list[dict]:
        return watchlist_service.list_items()

    @app.post("/watchlist")
    def add_to_watchlist(request: WatchlistAddRequest) -> dict:
        outcome = watchlist_service.add_symbol(request.symbol, request.exchange, request.note)
        if not outcome.get("ok"):
            raise HTTPException(status_code=404, detail=outcome.get("error"))
        return outcome

    @app.delete("/watchlist/{symbol}")
    def remove_from_watchlist(symbol: str, exchange: str = "NSE") -> dict:
        return watchlist_service.remove_symbol(symbol, exchange)

    @app.get("/sources/health")
    def source_health(refresh: bool = False) -> dict:
        if refresh:
            return default_registry().health_check_all()
        with session_scope() as session:
            rows = session.scalars(select(DataSource)).all()
            return {
                r.name: {"status": r.status, "last_checked": str(r.last_checked_at),
                         "last_success": str(r.last_success_at), "error": r.last_error}
                for r in rows
            }

    @app.get("/settings/jobs")
    def jobs() -> dict[str, bool]:
        return scheduler_service.job_states()

    @app.post("/settings/jobs")
    def toggle_job(request: JobToggleRequest) -> dict:
        try:
            scheduler_service.set_enabled(request.job, request.enabled)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"ok": True, "states": scheduler_service.job_states()}

    return app


app = create_app()
