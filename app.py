"""Streamlit dashboard entry: streamlit run app.py  (or run_dashboard.bat)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st

from database.connection import init_db
from frontend import design, market, theme
from frontend.pages import dashboard, engineering, overview, scouting, system

PAGES = {
    "Dashboard": dashboard.render,
    "Stock Scout": scouting.render_stock_scout,
    "NSE Screener": scouting.render_nse_screener,
    "BSE Screener": scouting.render_bse_screener,
    "Company Research": engineering.render_company_research,
    "Watchlist": engineering.render_watchlist,
    "Alerts": system.render_alerts,
    "Research History": engineering.render_history,
    "Settings": system.render_settings,
    "About": None,  # rendered inline below
}

# Old sidebar names from before the redesign still resolve.
ALIASES = {
    "Main Overview": "Dashboard",
    "NSE Stock Screener": "NSE Screener",
    "BSE Stock Screener": "BSE Screener",
    "Multibagger Watchlist": "Watchlist",
}


def render_about(st) -> None:
    st.title("About")
    st.markdown(
        "Multibagger Scout AI is a free-first Indian stock research platform. "
        "It runs eight specialist research agents (scout, fundamental, technical, business, "
        "valuation, risk, news, scoring) over free data sources and stores every output "
        "with its own date.")
    st.markdown(
        "- **Universe:** all NSE-listed equities (2,404) refreshed in weekday rotation batches; "
        "BSE source integration is still pending.\n"
        "- **Data:** free connectors (Yahoo Finance, NSE archives, RSS news). Data may be "
        "delayed or incomplete; every figure carries its source date.\n"
        "- **Scores:** explainable 100-point research scores. Risk score means higher = more risk. "
        "Governance items (pledging, auditors, related parties) are unassessed - no free "
        "verifiable source.\n"
        "- **Not advice:** research only. No trades are placed.\n"
        "- **Hosted updates:** a GitHub Actions workflow refreshes one batch each weekday and "
        "commits per-stock snapshots; the hosted database resets on restart, snapshots are the "
        "durable record.")
    st.divider()
    system.render_source_health(st)


@st.cache_data(ttl=1800, show_spinner=False)
def _index_levels() -> dict:
    return market.index_levels()


def data_status_pill() -> str:
    try:
        from data.connectors.yfinance_connector import YFinanceConnector
        ok = YFinanceConnector().health_check().ok
    except Exception:
        ok = False
    return "Data: free feed OK (quotes may be delayed)" if ok else "Data: feed degraded (free feed check failed)"


def main() -> None:
    init_db()
    theme.apply_theme(st)

    with st.sidebar:
        st.markdown(
            f'<div class="mb-brand" style="padding:6px 2px 12px 2px;">{design.LOGO_SVG}'
            '<div><div class="name" style="font-size:1.05rem;">MULTIBAGGER<br/>SCOUT AI</div>'
            '<div class="tag">Smart Research. Smarter Investing.</div></div></div>',
            unsafe_allow_html=True)
        names = list(PAGES)
        requested = ALIASES.get(st.query_params.get("page"), st.query_params.get("page"))
        default = names.index(requested) if requested in names else 0
        page = st.radio("Navigate", names, index=default, label_visibility="collapsed")
        st.query_params["page"] = page
        alert_count = 0
        try:
            from sqlalchemy import func, select
            from database.connection import session_scope
            from database.models import Alert
            with session_scope() as session:
                alert_count = session.scalar(
                    select(func.count(Alert.id)).where(Alert.status == "open")) or 0
        except Exception:
            pass
        if alert_count:
            st.caption(f"\U0001F514 {alert_count} open alert{'s' if alert_count != 1 else ''}")
        levels = _index_levels()
        market.render_sidebar_widget(st, levels, market.market_status(levels))
        st.caption("Research only. No trades. Free data may be delayed or incomplete.")

    design.header(st, ["\U0001F1EE\U0001F1F3 NSE + BSE", data_status_pill(), "Free Edition"])

    renderer = PAGES[page]
    if renderer is None:
        render_about(st)
    else:
        renderer(st)


if __name__ == "__main__":
    main()
else:
    # `streamlit run app.py` imports the module at top level.
    main()
