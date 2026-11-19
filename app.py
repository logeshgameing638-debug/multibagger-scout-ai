"""Streamlit dashboard entry: streamlit run app.py  (or run_dashboard.bat)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st

from database.connection import init_db
from frontend import theme
from frontend.pages import engineering, overview, research, scouting, system

PAGES = {
    "Main Overview": overview.render,
    "Stock Scout": scouting.render_stock_scout,
    "NSE Stock Screener": scouting.render_nse_screener,
    "BSE Stock Screener": scouting.render_bse_screener,
    "Fundamental Analysis": research.render_fundamental,
    "Technical Analysis": research.render_technical,
    "Business Quality": research.render_business,
    "Valuation": research.render_valuation,
    "Risk Analysis": research.render_risk,
    "News Intelligence": research.render_news,
    "Stock Ranking": engineering.render_ranking,
    "Company Research": engineering.render_company_research,
    "Multibagger Watchlist": engineering.render_watchlist,
    "Research History": engineering.render_history,
    "Alerts": system.render_alerts,
    "Settings": system.render_settings,
    "Data Source Health": system.render_source_health,
}


def main() -> None:
    init_db()
    theme.apply_theme(st)
    st.sidebar.title("Multibagger Scout AI")
    st.sidebar.caption("Research only. No trades. Free data may be delayed or incomplete.")
    names = list(PAGES)
    requested = st.query_params.get("page")
    default = names.index(requested) if requested in names else 0
    page = st.sidebar.radio("Navigate", names, index=default)
    PAGES[page](st)


if __name__ == "__main__":
    main()
else:
    # `streamlit run app.py` imports the module at top level.
    main()
