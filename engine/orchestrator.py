"""Final research and decision engine (master orchestrator).

Pipeline per company: validate identity -> collect data -> run eight agents ->
validate outputs -> record conflicts/missing -> scores -> rank -> report ->
store -> alerts. Each agent failure degrades the run to 'partial', never
silently invents output.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
from sqlalchemy import select

from agents import business_agent, fundamental_agent, news_agent, risk_agent, scoring_agent, technical_agent, valuation_agent
from agents.base import AgentResult, run_recorded
from data.connectors import default_registry
from data.validation import validate_bse_symbol, validate_nse_symbol
from database.connection import session_scope
from database.models import (
    Alert,
    BusinessAnalysis,
    Company,
    FinancialStatement,
    MarketPrice,
    ResearchScore,
    RiskFinding,
)
from engine.ranking import classify, combine_scores


def _store_statements(company_id: int, payload: dict, source: str) -> int:
    stored = 0
    with session_scope() as session:
        for period_type, statements in payload.items():
            for statement_type, periods in statements.items():
                for period_end, metrics in periods.items():
                    for metric, value in metrics.items():
                        exists = session.scalar(
                            select(FinancialStatement).where(
                                FinancialStatement.company_id == company_id,
                                FinancialStatement.period_type == period_type,
                                FinancialStatement.period_end == pd.Timestamp(period_end),
                                FinancialStatement.statement_type == statement_type,
                                FinancialStatement.metric == metric,
                                FinancialStatement.source == source,
                            )
                        )
                        if exists is None:
                            session.add(
                                FinancialStatement(
                                    company_id=company_id,
                                    period_type=period_type,
                                    period_end=pd.Timestamp(period_end),
                                    statement_type=statement_type,
                                    metric=metric,
                                    value=value,
                                    source=source,
                                )
                            )
                            stored += 1
    return stored


def _store_prices(company_id: int, frame: pd.DataFrame, source: str) -> int:
    stored = 0
    with session_scope() as session:
        for ts, row in frame.iterrows():
            ts_py = pd.Timestamp(ts).to_pydatetime().replace(tzinfo=None)
            exists = session.scalar(
                select(MarketPrice).where(
                    MarketPrice.company_id == company_id,
                    MarketPrice.ts == ts_py,
                    MarketPrice.interval == "1d",
                )
            )
            if exists is None:
                session.add(
                    MarketPrice(
                        company_id=company_id,
                        ts=ts_py,
                        interval="1d",
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=float(row["volume"]),
                        source=source,
                    )
                )
                stored += 1
    return stored


def research_company(symbol: str, exchange: str = "NSE", generate_report: bool = True,
                     sources_ok: dict[str, bool] | None = None) -> dict:
    """Run the complete research pipeline for one company. Returns a summary
    dict with each agent's real status."""
    exchange = exchange.upper()
    symbol = symbol.strip().upper()
    valid = validate_nse_symbol(symbol) if exchange == "NSE" else validate_bse_symbol(symbol)
    if not valid:
        return {"symbol": symbol, "exchange": exchange, "status": "failed", "error": "invalid symbol format"}

    registry = default_registry()
    yf = registry.get("yahoo_finance")
    agent_statuses: dict[str, str] = {}
    started = datetime.now(timezone.utc)

    # --- identity + collection -------------------------------------------
    info_result = yf.get_info(symbol, exchange)
    info = info_result.data if info_result.ok else {}
    name = info.get("longName", symbol)
    sector = info.get("sector")

    with session_scope() as session:
        company = session.scalar(
            select(Company).where(Company.symbol == symbol, Company.exchange == exchange)
        )
        if company is None:
            company = Company(symbol=symbol, exchange=exchange, name=name)
            session.add(company)
            session.flush()
        company.name = name
        company.sector = sector
        company.industry = info.get("industry")
        company.market_cap = info.get("marketCap")
        company.updated_at = datetime.now(timezone.utc)
        company_id = company.id

    history_result = yf.get_history(symbol, exchange, period="5y", interval="1d")
    frame = history_result.data["frame"] if history_result.ok else pd.DataFrame()
    if history_result.ok:
        _store_prices(company_id, frame, yf.name)

    statements_result = yf.get_financial_statements(symbol, exchange)
    statements = statements_result.data if statements_result.ok else {"annual": {}, "quarterly": {}}
    if statements_result.ok:
        _store_statements(company_id, statements, yf.name)

    sources_ok = dict(sources_ok or {})
    sources_ok.setdefault("yahoo_finance", info_result.ok or history_result.ok)
    sources_ok.setdefault("nse_archives", False)
    sources_ok.setdefault("bse_site", False)
    sources_ok.setdefault("rss_news", False)

    # --- eight agents ------------------------------------------------------
    fund_result = run_recorded(
        "fundamental_analysis",
        lambda: fundamental_agent.analyze(statements, info, sector),
        company_id=company_id,
        input_summary=f"{symbol}:{exchange}",
        required_keys=["growth", "profitability", "balance_sheet", "cash_flow"],
    )
    agent_statuses["fundamental"] = fund_result.status

    tech_result = run_recorded(
        "technical_analysis",
        lambda: technical_agent.analyze(frame),
        company_id=company_id,
        input_summary=f"{symbol}:{exchange} rows={len(frame)}",
        required_keys=["daily", "assessment"],
    )
    agent_statuses["technical"] = tech_result.status

    biz_result = run_recorded(
        "business_quality",
        lambda: business_agent.analyze(fund_result.data, info),
        company_id=company_id,
        input_summary=f"{symbol}:{exchange}",
        required_keys=["classification"],
    )
    agent_statuses["business"] = biz_result.status

    price = None
    if history_result.ok and not frame.empty:
        price = float(frame["close"].iloc[-1])
    val_result = run_recorded(
        "valuation",
        lambda: valuation_agent.analyze(info, fund_result.data, price),
        company_id=company_id,
        input_summary=f"{symbol}:{exchange}",
        required_keys=["multiples"],
    )
    agent_statuses["valuation"] = val_result.status

    risk_result = run_recorded(
        "risk_analysis",
        lambda: risk_agent.analyze(fund_result.data, tech_result.data, val_result.data, info),
        company_id=company_id,
        input_summary=f"{symbol}:{exchange}",
        required_keys=["classification", "findings"],
    )
    agent_statuses["risk"] = risk_result.status

    news_result = run_recorded(
        "news_intelligence",
        lambda: news_agent.analyze(name, symbol, company_id),
        company_id=company_id,
        input_summary=f"{symbol}:{exchange}",
    )
    agent_statuses["news"] = news_result.status
    sources_ok["rss_news"] = news_result.status in {"success", "partial"}

    score_result = run_recorded(
        "scoring",
        lambda: scoring_agent.analyze(
            fund_result.data, tech_result.data, biz_result.data, val_result.data,
            risk_result.data, sources_ok,
            news_items=news_result.data.get("stored_new", 0),
        ),
        company_id=company_id,
        input_summary=f"{symbol}:{exchange}",
        required_keys=["fundamental", "technical", "data_confidence", "risk"],
    )
    agent_statuses["scoring"] = score_result.status

    # --- combine + classify -------------------------------------------------
    f_score = score_result.data["fundamental"]["score"]
    t_score = score_result.data["technical"]["score"]
    dc_score = score_result.data["data_confidence"]["score"]
    r_score = score_result.data["risk"]["score"]
    combined = combine_scores(f_score, t_score)
    labels = classify(
        combined["balanced"], f_score, t_score, r_score,
        risk_result.data.get("classification"), dc_score,
        biz_result.data.get("classification"),
        val_result.data.get("margin_of_safety_vs_base_case"),
    )

    explanation = {
        "fundamental": score_result.data["fundamental"]["explanation"],
        "technical": score_result.data["technical"]["explanation"],
        "data_confidence": score_result.data["data_confidence"]["explanation"],
        "risk": score_result.data["risk"]["explanation"],
        "labels": labels,
        "weights": combined.get("weights"),
    }

    # --- persist ------------------------------------------------------------
    import json as _json

    with session_scope() as session:
        run_id = score_result.data.get("_run_id")
        score_row = ResearchScore(
            company_id=company_id,
            run_id=run_id,
            fundamental_score=f_score,
            technical_score=t_score,
            data_confidence=dc_score,
            risk_score=r_score,
            long_term_score=combined["long_term"],
            short_term_score=combined["short_term"],
            balanced_score=combined["balanced"],
            classification=",".join(labels),
            explanation_json=_json.dumps(explanation, default=str),
        )
        session.add(score_row)
        session.flush()
        score_id = score_row.id

        session.add(
            BusinessAnalysis(
                company_id=company_id,
                run_id=biz_result.data.get("_run_id"),
                classification=biz_result.data.get("classification", "insufficient_evidence"),
                summary="; ".join(biz_result.data.get("evidence", []))[:2000],
                evidence_json=_json.dumps(biz_result.data.get("evidence", [])),
            )
        )
        for finding in risk_result.data.get("findings", []):
            session.add(
                RiskFinding(
                    company_id=company_id,
                    category=finding["category"],
                    severity=finding["severity"],
                    classification=risk_result.data.get("classification", "UNASSESSED"),
                    evidence=finding["evidence"],
                    source=finding["source"],
                )
            )
        # Risk escalation alert on HIGH/CRITICAL.
        if risk_result.data.get("classification") in {"HIGH", "CRITICAL"}:
            session.add(
                Alert(
                    company_id=company_id,
                    alert_type="risk_escalation",
                    message=(
                        f"{symbol} risk classification {risk_result.data['classification']}: "
                        + "; ".join(f["evidence"] for f in risk_result.data.get("findings", []))[:400]
                    ),
                    severity="high" if risk_result.data["classification"] == "HIGH" else "critical",
                )
            )

    # --- report -------------------------------------------------------------
    report_paths: dict[str, str] = {}
    if generate_report:
        from engine.report_generator import generate_company_report

        bundle = {
            "symbol": symbol, "exchange": exchange, "name": name, "info": info,
            "fundamentals": fund_result.data, "technicals": tech_result.data,
            "business": biz_result.data, "valuation": val_result.data,
            "risk": risk_result.data, "news": news_result.data,
            "scores": {"fundamental": f_score, "technical": t_score,
                       "data_confidence": dc_score, "risk": r_score, **combined},
            "labels": labels, "explanation": explanation,
            "agent_statuses": agent_statuses,
            "generated_at": str(datetime.now(timezone.utc)),
        }
        report_paths = generate_company_report(bundle, company_id)

    overall = "success" if all(s == "success" for s in agent_statuses.values()) else "partial"
    if fund_result.status == "failed" and tech_result.status == "failed":
        overall = "failed"
    return {
        "symbol": symbol,
        "exchange": exchange,
        "status": overall,
        "agent_statuses": agent_statuses,
        "scores": {"fundamental": f_score, "technical": t_score,
                   "data_confidence": dc_score, "risk": r_score, **combined},
        "labels": labels,
        "score_id": score_id,
        "reports": report_paths,
        "duration_seconds": (datetime.now(timezone.utc) - started).total_seconds(),
    }
