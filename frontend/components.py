"""Shared dashboard components: score cards, tables, charts, data access."""
from __future__ import annotations

import json

import pandas as pd
import plotly.graph_objects as go
from sqlalchemy import desc, select

from database.connection import session_scope
from database.models import AgentOutput, AgentRun, Company, MarketPrice, ResearchScore


def score_cards(st, scores: dict) -> None:
    cols = st.columns(5)
    cards = [
        ("Fundamental", scores.get("fundamental_score"), "higher is stronger"),
        ("Technical", scores.get("technical_score"), "higher is stronger"),
        ("Data confidence", scores.get("data_confidence"), "coverage quality"),
        ("Risk", scores.get("risk_score"), "HIGHER = MORE RISK"),
        ("Balanced", scores.get("balanced_score"), "0.5 long + 0.5 short"),
    ]
    for col, (label, value, hint) in zip(cols, cards):
        display = "n/a" if value is None else f"{value:.1f}"
        col.markdown(
            f'<div class="score-card"><div class="value">{display}</div>'
            f'<div class="label">{label}<br><small>{hint}</small></div></div>',
            unsafe_allow_html=True,
        )


def risk_coverage(st, company_id: int) -> None:
    """Show risk coverage next to score cards so a low/zero risk score is
    never mistaken for 'governance cleared'."""
    output = latest_agent_output(company_id, "risk")
    if not output:
        st.caption("Risk coverage: no risk run yet - risk is not assessed.")
        return
    data = output.get("data", {})
    classification = data.get("classification", "UNASSESSED")
    unassessed = data.get("unassessed_governance_items", [])
    coverage = data.get("coverage", "")
    if classification in {"UNASSESSED", "LOW"} or unassessed:
        st.warning(
            f"Risk: {classification}. {coverage or 'Quantitative checks only.'} "
            f"{len(unassessed)} governance items are UNASSESSED (no free verifiable source) - "
            "a low or zero risk score is not an all-clear."
        )
    else:
        st.caption(f"Risk: {classification} from measured findings. {coverage}")


def company_options() -> list[tuple[str, int]]:
    with session_scope() as session:
        rows = session.scalars(select(Company).order_by(Company.symbol)).all()
        return [(f"{c.symbol} ({c.exchange}) - {c.name}", c.id) for c in rows]


def latest_scores(company_id: int | None = None) -> pd.DataFrame:
    """Latest per-stock scores.

    Primary source on the hosted app: the committed rotation snapshots
    (data/snapshots/*.json). The hosted SQLite DB is wiped on every restart,
    so DB scores are only a fallback for on-demand research done this session.
    """
    from services.snapshots import load_snapshots

    snapshots = load_snapshots()
    snap_records = []
    for symbol, snap in snapshots.items():
        scores = snap.get("scores") or {}
        if not scores:
            continue
        snap_records.append({
            "symbol": symbol,
            "name": snap.get("name"),
            "fundamental": scores.get("fundamental"),
            "technical": scores.get("technical"),
            "data_confidence": scores.get("data_confidence"),
            "risk(higher=worse)": scores.get("risk"),
            "long_term": scores.get("long_term"),
            "short_term": scores.get("short_term"),
            "balanced": scores.get("balanced"),
            "labels": snap.get("classification"),
            "created_at": snap.get("updated_at"),
        })
    if snap_records:
        return pd.DataFrame(snap_records)

    with session_scope() as session:
        query = (
            select(ResearchScore, Company.symbol, Company.name)
            .join(Company, Company.id == ResearchScore.company_id)
            .order_by(desc(ResearchScore.created_at))
        )
        if company_id is not None:
            query = query.where(ResearchScore.company_id == company_id)
        rows = session.execute(query.limit(300)).all()
    records = [
        {
            "symbol": symbol, "name": name,
            "fundamental": s.fundamental_score, "technical": s.technical_score,
            "data_confidence": s.data_confidence, "risk(higher=worse)": s.risk_score,
            "long_term": s.long_term_score, "short_term": s.short_term_score,
            "balanced": s.balanced_score, "labels": s.classification,
            "created_at": str(s.created_at),
        }
        for s, symbol, name in rows
    ]
    return pd.DataFrame(records)


def latest_agent_output(company_id: int, agent_name: str) -> dict | None:
    with session_scope() as session:
        row = session.execute(
            select(AgentOutput.output_json)
            .join(AgentRun, AgentRun.id == AgentOutput.run_id)
            .where(AgentRun.agent_name == agent_name, AgentOutput.company_id == company_id)
            .order_by(desc(AgentOutput.created_at))
            .limit(1)
        ).first()
    if row is None:
        return None
    return json.loads(row[0])


def price_frame(company_id: int, limit: int = 500) -> pd.DataFrame:
    with session_scope() as session:
        rows = session.scalars(
            select(MarketPrice)
            .where(MarketPrice.company_id == company_id, MarketPrice.interval == "1d")
            .order_by(desc(MarketPrice.ts))
            .limit(limit)
        ).all()
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(
        [
            {"ts": r.ts, "open": r.open, "high": r.high, "low": r.low,
             "close": r.close, "volume": r.volume}
            for r in rows
        ]
    ).sort_values("ts").set_index("ts")
    return frame


def candlestick_chart(frame: pd.DataFrame, title: str) -> go.Figure:
    figure = go.Figure(
        data=[
            go.Candlestick(
                x=frame.index, open=frame["open"], high=frame["high"],
                low=frame["low"], close=frame["close"], name="price",
                increasing_line_color="#22c55e", decreasing_line_color="#ef4444",
            )
        ]
    )
    figure.update_layout(
        title=title, template="plotly_dark", paper_bgcolor="#0b1220",
        plot_bgcolor="#0b1220", xaxis_rangeslider_visible=False, height=420,
    )
    return figure
