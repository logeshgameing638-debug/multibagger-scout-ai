"""Pydantic schemas for the API."""
from __future__ import annotations

from pydantic import BaseModel, Field


class ScanRequest(BaseModel):
    index: str = "NIFTY 50"
    limit: int = Field(default=50, ge=1, le=500)
    custom_symbols: list[str] | None = None  # ["RELIANCE:NSE", "500325:BSE"]
    generate_reports: bool = False


class ResearchRequest(BaseModel):
    symbol: str
    exchange: str = "NSE"


class WatchlistAddRequest(BaseModel):
    symbol: str
    exchange: str = "NSE"
    note: str = ""


class JobToggleRequest(BaseModel):
    job: str
    enabled: bool


class CompanyOut(BaseModel):
    symbol: str
    exchange: str
    name: str
    sector: str | None = None
    industry: str | None = None
    market_cap: float | None = None


class ScoreOut(BaseModel):
    symbol: str
    fundamental_score: float | None
    technical_score: float | None
    data_confidence: float | None
    risk_score: float | None
    long_term_score: float | None
    short_term_score: float | None
    balanced_score: float | None
    classification: str | None
    created_at: str
