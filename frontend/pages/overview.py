"""Page 1: Main Overview."""
from __future__ import annotations

import pandas as pd
from sqlalchemy import func, select

from database.connection import session_scope
from database.models import AgentRun, Alert, Company, MarketPrice, ResearchScore
from frontend import components


def render(st) -> None:
    st.title("Multibagger Scout AI")
    st.caption("Free-first Indian stock research. Analysis only - no trades are placed.")

    with session_scope() as session:
        total_companies = session.scalar(select(func.count(Company.id))) or 0
        status_counts = dict(
            session.execute(
                select(Company.research_status, func.count()).group_by(Company.research_status)
            ).all()
        )
        total_prices = session.scalar(select(func.count(MarketPrice.id))) or 0
        open_alerts = session.scalar(
            select(func.count(Alert.id)).where(Alert.status == "open")
        ) or 0
        latest_price_ts = session.scalar(select(func.max(MarketPrice.ts)))
        recent_runs = session.scalars(
            select(AgentRun).order_by(AgentRun.id.desc()).limit(8)
        ).all()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Companies in library", total_companies)
    c2.metric("Research complete", status_counts.get("complete", 0))
    c3.metric("Price rows stored", total_prices)
    c4.metric("Open alerts", open_alerts)
    st.caption(
        "Research status across the library: "
        + ", ".join(f"{name} {count}" for name, count in sorted(status_counts.items()))
        + f". Price data as of {str(latest_price_ts)[:10] if latest_price_ts else 'no data yet'}."
    )

    st.subheader("Hosted daily updates (rotation)")
    from services.snapshots import coverage_summary

    coverage = coverage_summary()
    if coverage is None:
        st.info(
            "No hosted rotation data yet. Once the daily GitHub Actions run has "
            "committed snapshots, coverage appears here."
        )
    else:
        r1, r2, r3 = st.columns(3)
        r1.metric(
            "Stocks refreshed this cycle",
            f"{coverage['stocks_with_data']} of {coverage['universe_size']}",
        )
        r2.metric("Coverage", f"{coverage['coverage_pct']}%")
        r3.metric("Last update run", coverage["last_run_at"] or "unknown")
        st.caption(
            "Free hosting cannot scan the whole market every day: one batch is "
            "refreshed each weekday, so every stock carries its own date. "
            f"Data spans {coverage['oldest_data']} to {coverage['newest_data']}. "
            f"Statuses: {coverage['complete']} complete, {coverage['partial']} partial, "
            f"{coverage['unavailable']} unavailable (retried next cycle). "
            "A full scan of every stock completes over several weeks, not daily."
        )

    st.subheader("Top research candidates (latest scores)")
    scores = components.latest_scores()
    if scores.empty:
        st.info("No research yet. Run a scan from the Stock Scout page.")
    else:
        latest = scores.drop_duplicates("symbol").sort_values(
            "balanced", ascending=False, na_position="last"
        )
        st.dataframe(latest.head(15), use_container_width=True, hide_index=True)

        col_a, col_b, col_c = st.columns(3)
        col_a.markdown("**Fundamental leaders**")
        col_a.dataframe(latest.nlargest(5, "fundamental")[["symbol", "fundamental"]], hide_index=True)
        col_b.markdown("**Technical leaders**")
        col_b.dataframe(latest.nlargest(5, "technical")[["symbol", "technical"]], hide_index=True)
        col_c.markdown("**High-risk companies**")
        col_c.dataframe(latest.nlargest(5, "risk(higher=worse)")[["symbol", "risk(higher=worse)"]], hide_index=True)
        st.caption(
            "Risk scores cover quantitative checks only (debt, cash flow, profit quality, "
            "valuation, volatility, liquidity). Governance items (pledging, auditor changes, "
            "related-party transactions, regulatory actions) have no free verifiable source and "
            "stay UNASSESSED - a low risk score is not an all-clear."
        )

        st.markdown("**Newly detected opportunities**")
        opportunities = latest[latest["labels"].fillna("").str.contains("multibagger|attractive_valuation")]
        if opportunities.empty:
            st.caption("None in the latest run.")
        else:
            st.dataframe(opportunities[["symbol", "labels", "balanced"]], hide_index=True)

    st.subheader("Agent execution status (real, most recent first)")
    if not recent_runs:
        st.caption("No agent runs yet.")
    else:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "agent": r.agent_name, "status": r.status,
                        "started": str(r.started_at), "finished": str(r.finished_at),
                        "error": (r.error or "")[:120],
                    }
                    for r in recent_runs
                ]
            ),
            use_container_width=True, hide_index=True,
        )
