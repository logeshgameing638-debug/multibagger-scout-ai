"""Pages 2-4: Stock Scout, NSE Stock Screener, BSE Stock Screener."""
from __future__ import annotations

import pandas as pd


def render_stock_scout(st) -> None:
    st.title("Stock Scout")
    st.caption("Discover and shortlist listed companies, then run full research.")

    mode = st.radio("Source", ["NIFTY 50", "NIFTY NEXT 50", "NIFTY 100", "Custom symbols"], horizontal=True)
    custom: list[tuple[str, str]] | None = None
    index = mode
    if mode == "Custom symbols":
        raw = st.text_area(
            "One per line as SYMBOL:EXCHANGE (exchange NSE or BSE)",
            placeholder="RELIANCE:NSE\nTCS:NSE\n500325:BSE",
        )
        custom = []
        for line in raw.splitlines():
            if not line.strip():
                continue
            symbol, _, exchange = line.partition(":")
            custom.append((symbol.strip().upper(), (exchange.strip() or "NSE").upper()))

    limit = st.slider("Max candidates", 5, 100, 50, step=5)
    st.caption("A 50-stock run fetches real data per stock and can take several minutes on a slow connection.")

    if st.button("Run scan", type="primary"):
        from services.scanner import run_scan

        progress = st.progress(0.0, text="starting")
        status = st.empty()

        def on_progress(position: int, total: int, symbol: str) -> None:
            progress.progress(position / max(total, 1), text=f"{position}/{total}: {symbol}")

        outcome = run_scan(index=index, limit=limit, custom_symbols=custom)
        status.write(
            f"Scan {outcome['status']}: {outcome.get('researched', 0)}/{outcome.get('discovered', 0)} researched."
        )
        if outcome.get("failed_symbols"):
            st.warning(f"Failed: {', '.join(outcome['failed_symbols'])}")
        if outcome.get("error"):
            st.error(outcome["error"])

    st.subheader("Full-market universe (NSE listed equities + BSE latest-session instruments)")
    st.caption(
        "NSE loads from the official equity master (EQ series); BSE loads from the official "
        "daily common bhavcopy - the instruments of the latest trading session (about 5,100 "
        "STK rows on 18 Nov 2026), not a registry of every listed BSE company; suspended or "
        "untraded names can be absent, and the scrip-master CSV path remains a configurable "
        "override. Dual-listed companies are deduplicated by ISIN. Per-stock "
        "fundamentals come from Yahoo Finance (.NS / .BO); symbols Yahoo cannot resolve are "
        "recorded unavailable, never fabricated. Scanning runs in resumable batches: every "
        "stock ends up complete, partial or unavailable, and the coverage count below is "
        "against the whole loaded universe - a batch is never presented as a full-market "
        "result. A full-market run takes many hours by design to keep provider load bounded."
    )
    from services import universe as universe_service

    col_u1, col_u2 = st.columns(2)
    if col_u1.button("Load NSE listed universe"):
        with st.spinner("Fetching NSE equity master..."):
            result = universe_service.load_nse_universe()
        if result.get("ok"):
            st.success(
                f"NSE universe loaded: {result['added']} new, "
                f"{result['linked_existing']} matched to existing by ISIN, "
                f"{result['skipped_non_equity']} non-equity series skipped."
            )
        else:
            st.error(f"NSE universe load failed: {result.get('error')}")
    if col_u2.button("Load BSE universe"):
        with st.spinner("Fetching BSE scrip master..."):
            result = universe_service.load_bse_universe()
        if result.get("ok"):
            st.success(f"BSE universe loaded: {result['added']} new, "
                       f"{result.get('linked_existing', 0)} matched to existing by ISIN.")
        else:
            st.error(f"BSE universe load failed: {result.get('error')} "
                     "(the BSE master URL is configurable in settings)")

    progress_info = universe_service.universe_progress()
    st.caption(
        f"Universe coverage: {progress_info['total']} instruments in library (NSE listed + BSE session scope) | "
        + " | ".join(f"{k}: {v}" for k, v in sorted(progress_info["by_status"].items()))
    )

    batch_size = st.slider("Batch size (stocks per run)", 5, 100, 25, step=5, key="universe_batch")
    if st.button("Scan next pending batch", key="universe_scan"):
        bar = st.progress(0.0, text="starting batch")

        def _on_progress(position: int, total: int, symbol: str) -> None:
            bar.progress(position / max(total, 1), text=f"{position}/{total}: {symbol}")

        outcome = universe_service.scan_universe(batch_size=batch_size, sleep_seconds=1.0,
                                                 on_progress=_on_progress)
        st.write(
            f"Batch done: {outcome['complete']} complete, {outcome['partial']} partial, "
            f"{outcome['failed']} unavailable (of {outcome['batch']}). "
            f"Overall: {outcome['progress']['by_status']}"
        )

    st.subheader("Latest discovery run")
    from sqlalchemy import select

    from database.connection import session_scope
    from database.models import AgentOutput, AgentRun

    with session_scope() as session:
        row = session.execute(
            select(AgentOutput.output_json)
            .join(AgentRun, AgentRun.id == AgentOutput.run_id)
            .where(AgentRun.agent_name == "stock_scout")
            .order_by(AgentOutput.id.desc())
            .limit(1)
        ).first()
    if row is None:
        st.info("No discovery run yet.")
        return
    import json

    output = json.loads(row[0])
    candidates = output.get("data", {}).get("candidates", [])
    st.caption(f"Run status: {output.get('status')} | missing: {output.get('missing') or 'none'}")
    if candidates:
        st.dataframe(pd.DataFrame(candidates), use_container_width=True, hide_index=True)


def _screener(st, exchange: str) -> None:
    st.title(f"{exchange} Stock Screener")
    from sqlalchemy import select

    from database.connection import session_scope
    from database.models import Company, ResearchScore

    with session_scope() as session:
        rows = session.execute(
            select(Company, ResearchScore)
            .join(ResearchScore, ResearchScore.company_id == Company.id, isouter=True)
            .where(Company.exchange == exchange)
            .order_by(Company.symbol)
        ).all()
    if not rows:
        st.info(f"No {exchange} companies in the database yet. Run a scan from Stock Scout.")
        return

    records = [
        {
            "symbol": c.symbol, "name": c.name, "sector": c.sector,
            "market_cap": c.market_cap,
            "balanced": s.balanced_score if s else None,
            "fundamental": s.fundamental_score if s else None,
            "technical": s.technical_score if s else None,
            "risk(higher=worse)": s.risk_score if s else None,
        }
        for c, s in rows
    ]
    frame = pd.DataFrame(records)

    col1, col2, col3 = st.columns(3)
    search = col1.text_input("Search symbol/name")
    sector = col2.selectbox("Sector", ["all"] + sorted({r for r in frame["sector"].dropna()}))
    min_bal = col3.slider("Min balanced score", 0, 100, 0)
    filtered = frame
    if search:
        mask = filtered["symbol"].str.contains(search.upper()) | filtered["name"].str.contains(search, case=False)
        filtered = filtered[mask]
    if sector != "all":
        filtered = filtered[filtered["sector"] == sector]
    filtered = filtered[filtered["balanced"].fillna(0) >= min_bal]

    st.dataframe(filtered, use_container_width=True, hide_index=True)
    st.download_button(
        "Export CSV", filtered.to_csv(index=False).encode(), f"{exchange}_screener.csv", "text/csv"
    )


def render_nse_screener(st) -> None:
    _screener(st, "NSE")


def render_bse_screener(st) -> None:
    _screener(st, "BSE")
