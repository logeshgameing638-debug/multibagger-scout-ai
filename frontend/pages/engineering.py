"""Pages 11-14: Stock Ranking, Company Research, Multibagger Watchlist, Research History."""
from __future__ import annotations

import json
import os

import pandas as pd
from sqlalchemy import desc, select

from database.connection import session_scope
from database.models import Company, ResearchReport, ResearchScore
from frontend import components


def render_ranking(st) -> None:
    st.title("Stock Ranking")
    scores = components.latest_scores()
    if scores.empty:
        st.info("No scores yet. Run a scan first.")
        return
    latest = scores.drop_duplicates("symbol")
    key = st.radio("Rank by", ["balanced", "long_term", "short_term"], horizontal=True)
    ranked = latest.sort_values(key, ascending=False, na_position="last")
    st.dataframe(ranked, use_container_width=True, hide_index=True)
    st.download_button("Export ranking CSV", ranked.to_csv(index=False).encode(), "ranking.csv", "text/csv")


def render_company_research(st) -> None:
    st.title("Company Research")
    options = components.company_options()
    if not options:
        st.info("No companies yet. Run a scan first.")
        return
    labels = [label for label, _ in options]
    choice = st.selectbox("Company", labels)
    company_id = dict(options)[choice]

    with session_scope() as session:
        company = session.get(Company, company_id)
        latest_score = session.scalar(
            select(ResearchScore)
            .where(ResearchScore.company_id == company_id)
            .order_by(desc(ResearchScore.created_at))
            .limit(1)
        )
        reports = session.scalars(
            select(ResearchReport)
            .where(ResearchReport.company_id == company_id)
            .order_by(desc(ResearchReport.created_at))
        ).all()

    st.subheader(f"{company.name} ({company.symbol}:{company.exchange})")
    st.caption(f"Sector: {company.sector or 'n/a'} | Industry: {company.industry or 'n/a'} | "
               f"Market cap: {company.market_cap or 'n/a'}")

    if st.button("Run fresh research now"):
        from engine.orchestrator import research_company

        with st.spinner("Running all eight agents..."):
            outcome = research_company(company.symbol, company.exchange)
        st.write(f"Status: {outcome['status']} | agents: {outcome['agent_statuses']}")
        st.rerun()

    if latest_score:
        components.score_cards(
            st,
            {
                "fundamental_score": latest_score.fundamental_score,
                "technical_score": latest_score.technical_score,
                "data_confidence": latest_score.data_confidence,
                "risk_score": latest_score.risk_score,
                "balanced_score": latest_score.balanced_score,
            },
        )
        st.caption(f"Long-term {latest_score.long_term_score} | Short-term {latest_score.short_term_score} "
                   f"| Labels: {latest_score.classification}")
        components.risk_coverage(st, company_id)
        with st.expander("Score explanations (every subscore)"):
            explanation = json.loads(latest_score.explanation_json or "{}")
            st.json(explanation)

    frame = components.price_frame(company_id)
    if not frame.empty:
        st.plotly_chart(components.candlestick_chart(frame.tail(250), "Price history"), use_container_width=True)

    st.markdown("**Reports**")
    if not reports:
        st.caption("No report files yet for this company. Click 'Run fresh research now' above "
                   "to generate HTML/CSV/JSON/PDF reports, or use the Research Company page.")
    seen: set[tuple[str, str]] = set()
    for report in reports:
        if (report.format, report.path) in seen:
            continue
        seen.add((report.format, report.path))
        if os.path.exists(report.path):
            with open(report.path, "rb") as fh:
                st.download_button(
                    f"Download {report.format.upper()} report", fh.read(),
                    file_name=os.path.basename(report.path), key=f"rep-{report.id}",
                )
        else:
            st.caption(f"{report.format}: {report.path}")


def render_watchlist(st) -> None:
    st.title("Multibagger Watchlist")
    st.caption("Multibagger = research hypothesis, never a guaranteed outcome.")
    from services import watchlist as wl_service

    items = wl_service.list_items()
    with st.form("add_watchlist"):
        col1, col2 = st.columns(2)
        symbol = col1.text_input("Symbol (must be researched first)")
        exchange = col2.selectbox("Exchange", ["NSE", "BSE"])
        if st.form_submit_button("Add"):
            outcome = wl_service.add_symbol(symbol, exchange)
            if outcome.get("ok"):
                st.success("Added" if not outcome.get("already_present") else "Already on the list")
            else:
                st.error(outcome.get("error"))
    if items:
        st.dataframe(pd.DataFrame(items), use_container_width=True, hide_index=True)
    else:
        st.info("Watchlist is empty. Candidates labelled potential_multibagger_hypothesis are added automatically after scans, or add manually above.")


def render_history(st) -> None:
    st.title("Research History")
    scores = components.latest_scores()
    if scores.empty:
        st.info("No research history yet.")
        return
    symbol = st.selectbox("Symbol", sorted(scores["symbol"].unique()))
    history = scores[scores["symbol"] == symbol].sort_values("created_at")
    st.dataframe(history, use_container_width=True, hide_index=True)
    if len(history) > 1:
        chart_frame = history.set_index(pd.to_datetime(history["created_at"]))[
            ["fundamental", "technical", "balanced", "risk(higher=worse)"]
        ]
        st.line_chart(chart_frame)
