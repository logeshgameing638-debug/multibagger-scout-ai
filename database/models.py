"""SQLAlchemy models. SQLite by default; column types stay PostgreSQL-compatible."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Company(Base):
    __tablename__ = "companies"
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    exchange: Mapped[str] = mapped_column(String(8))  # NSE / BSE
    name: Mapped[str] = mapped_column(String(255))
    sector: Mapped[str | None] = mapped_column(String(128), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(128), nullable=True)
    market_cap: Mapped[float | None] = mapped_column(Float, nullable=True)
    isin: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    instrument_type: Mapped[str] = mapped_column(String(24), default="equity")
    research_status: Mapped[str] = mapped_column(String(16), default="pending")  # pending/complete/partial/unavailable
    researched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    __table_args__ = (UniqueConstraint("symbol", "exchange", name="uq_company_symbol_exchange"),)


class ExchangeSymbol(Base):
    __tablename__ = "exchange_symbols"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    exchange: Mapped[str] = mapped_column(String(8))
    symbol: Mapped[str] = mapped_column(String(32))
    scrip_code: Mapped[str | None] = mapped_column(String(32), nullable=True)  # BSE code
    source: Mapped[str] = mapped_column(String(64))
    validated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint("exchange", "symbol", name="uq_exchange_symbol"),)


class MarketPrice(Base):
    __tablename__ = "market_prices"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime, index=True)
    interval: Mapped[str] = mapped_column(String(8), default="1d")
    open: Mapped[float | None] = mapped_column(Float, nullable=True)
    high: Mapped[float | None] = mapped_column(Float, nullable=True)
    low: Mapped[float | None] = mapped_column(Float, nullable=True)
    close: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(64))
    __table_args__ = (UniqueConstraint("company_id", "ts", "interval", name="uq_price_point"),)


class FinancialStatement(Base):
    """One row per metric per period. Historical rows are never overwritten:
    a new source for the same period inserts a new row keyed by source."""
    __tablename__ = "financial_statements"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    period_type: Mapped[str] = mapped_column(String(16))  # annual / quarterly
    period_end: Mapped[datetime] = mapped_column(DateTime, index=True)
    statement_type: Mapped[str] = mapped_column(String(16))  # income / balance / cashflow
    metric: Mapped[str] = mapped_column(String(64))
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    source: Mapped[str] = mapped_column(String(64))
    ingested_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (
        UniqueConstraint(
            "company_id", "period_type", "period_end", "statement_type", "metric", "source",
            name="uq_statement_metric",
        ),
    )


class FundamentalMetric(Base):
    __tablename__ = "fundamental_metrics"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    metric: Mapped[str] = mapped_column(String(64))
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    period_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    source: Mapped[str] = mapped_column(String(64))
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class TechnicalMetric(Base):
    __tablename__ = "technical_metrics"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime)
    timeframe: Mapped[str] = mapped_column(String(8), default="1d")
    metric: Mapped[str] = mapped_column(String(64))
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(64), default="computed")


class BusinessAnalysis(Base):
    __tablename__ = "business_analysis"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id"), nullable=True)
    classification: Mapped[str] = mapped_column(String(32))  # strong/average/weak/insufficient
    summary: Mapped[str] = mapped_column(Text, default="")
    evidence_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ValuationAnalysis(Base):
    __tablename__ = "valuation_analysis"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    method: Mapped[str] = mapped_column(String(64))
    fair_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    assumptions_json: Mapped[str] = mapped_column(Text, default="{}")
    source: Mapped[str] = mapped_column(String(64), default="computed")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class RiskFinding(Base):
    __tablename__ = "risk_findings"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    category: Mapped[str] = mapped_column(String(64))
    severity: Mapped[str] = mapped_column(String(16))  # info/low/moderate/high/critical
    classification: Mapped[str] = mapped_column(String(16))  # overall class at detection
    evidence: Mapped[str] = mapped_column(Text, default="")
    risk_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    source: Mapped[str] = mapped_column(String(64))
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class NewsArticle(Base):
    __tablename__ = "news_articles"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), nullable=True, index=True)
    headline: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(128))
    url: Mapped[str] = mapped_column(Text, unique=True)  # dedupe key
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sentiment: Mapped[str] = mapped_column(String(16), default="neutral")
    relevance: Mapped[str] = mapped_column(String(16), default="medium")
    verification_status: Mapped[str] = mapped_column(String(16), default="unverified")
    ingested_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AgentRun(Base):
    __tablename__ = "agent_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    agent_name: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(16))  # success/partial/failed
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    input_summary: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    outputs: Mapped[list["AgentOutput"]] = relationship(back_populates="run")


class AgentOutput(Base):
    __tablename__ = "agent_outputs"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("agent_runs.id"), index=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), nullable=True, index=True)
    output_json: Mapped[str] = mapped_column(Text, default="{}")
    valid: Mapped[bool] = mapped_column(Boolean, default=True)
    validation_errors: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    run: Mapped[AgentRun] = relationship(back_populates="outputs")


class ResearchScore(Base):
    __tablename__ = "research_scores"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id"), nullable=True)
    fundamental_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    technical_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    data_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)  # higher = more risk
    long_term_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    short_term_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    balanced_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    classification: Mapped[str | None] = mapped_column(String(64), nullable=True)
    explanation_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class ResearchReport(Base):
    __tablename__ = "research_reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id"), nullable=True)
    format: Mapped[str] = mapped_column(String(8))  # html / json / csv / pdf
    path: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Watchlist(Base):
    __tablename__ = "watchlists"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    kind: Mapped[str] = mapped_column(String(32), default="custom")  # multibagger / custom
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    items: Mapped[list["WatchlistItem"]] = relationship(back_populates="watchlist")


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    watchlist_id: Mapped[int] = mapped_column(ForeignKey("watchlists.id"), index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    added_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    note: Mapped[str] = mapped_column(Text, default="")
    watchlist: Mapped[Watchlist] = relationship(back_populates="items")
    __table_args__ = (UniqueConstraint("watchlist_id", "company_id", name="uq_watchlist_item"),)


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), nullable=True, index=True)
    alert_type: Mapped[str] = mapped_column(String(48))
    message: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(16), default="info")
    status: Mapped[str] = mapped_column(String(16), default="open")  # open / acknowledged
    triggered_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class DataSource(Base):
    __tablename__ = "data_sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    type: Mapped[str] = mapped_column(String(32))  # prices / listings / news / filings
    base_url: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="unknown")  # ok / degraded / down / unknown
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")


class DataQualityLog(Base):
    __tablename__ = "data_quality_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(64))
    check: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16))  # pass / warn / fail
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")


class PaperOrder(Base):
    """Simulated order for the paper-trading floor. Never reaches a broker:
    fills are computed from the latest free price feed and marked SIMULATED."""
    __tablename__ = "paper_orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    exchange: Mapped[str] = mapped_column(String(8), default="NSE")
    side: Mapped[str] = mapped_column(String(8))  # BUY / SELL
    qty: Mapped[int] = mapped_column(Integer)
    order_type: Mapped[str] = mapped_column(String(16), default="MARKET")  # simulated MARKET only
    status: Mapped[str] = mapped_column(String(16), default="open")  # open / filled / cancelled
    fill_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    target: Mapped[float | None] = mapped_column(Float, nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    filled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Decision(Base):
    """Floor 07 verdict on a researched company."""
    __tablename__ = "decisions"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), nullable=True, index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    verdict: Mapped[str] = mapped_column(String(16))  # approved / rejected / watchlist / paper_trade
    rationale: Mapped[str] = mapped_column(Text, default="")
    balanced_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class SchemaMigration(Base):
    __tablename__ = "schema_migrations"
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    applied_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


Index("ix_prices_company_interval_ts", MarketPrice.company_id, MarketPrice.interval, MarketPrice.__table__.c.ts.desc())
