"""The multi-floor trading building: eight working floor workspaces over the
same backend, orchestrator and database. Floor 00 is the command center;
floors 01-07 host the scanner, analyst, risk, paper-execution, monitoring,
portfolio and decision workspaces. Activity indicators light up only when a
real run happened recently - nothing here is a decorative mockup. Execution is
paper-only: no broker orders, no real money.
"""
from __future__ import annotations

import pandas as pd
from sqlalchemy import desc, func, select

from database.connection import session_scope
from database.models import (
    AgentRun,
    Company,
    Decision,
    NewsArticle,
    ResearchScore,
    RiskFinding,
)
from frontend import design
from frontend.pages import dashboard as dash_page
from frontend.pages import engineering, scouting, system
from services import building as building_service
from services import paper_trading
from services import watchlist as wl_service

FLOORS = [
    (0, "Command Center", "\U0001F3DB", "orchestrator, queue, database, health, logs"),
    (1, "Market Scanner", "\U0001F50D", "NSE/BSE discovery and screening"),
    (2, "AI Analyst", "\U0001F4CA", "fundamental, technical, statements, entry/exit research"),
    (3, "Risk Manager", "\U0001F6E1", "risk/reward, position sizing, exposure, approval"),
    (4, "Paper Executor", "\U0001F4DD", "SIMULATED orders only - never real trades"),
    (5, "Monitor & Alerts", "\U0001F514", "price, news and breakout alerts"),
    (6, "Portfolio Manager", "\U0001F4BC", "paper holdings, P&L, exposure"),
    (7, "Decision Engine", "\U0001F3AF", "ranks candidates, records verdicts, explains"),
]

FLOOR_PAGE_NAMES = {n: f"Floor {n:02d} · {name}" for n, name, _, _ in FLOORS}


def _floor_chrome(st, floor_no: int) -> None:
    """Floor header: live status chip, run stats, data-source note."""
    name, icon, purpose = FLOORS[floor_no][1], FLOORS[floor_no][2], FLOORS[floor_no][3]
    activity = building_service.floor_activity().get(floor_no, {})
    active = activity.get("active")
    chip = ('<span style="color:#22c55e;">&#9679; ACTIVE NOW</span>' if active
            else '<span style="color:#64748b;">&#9679; idle</span>')
    st.markdown(
        f'<div class="mb-card"><h4>{icon} Floor {floor_no:02d} - {name} &nbsp; {chip}</h4>'
        f'<div class="muted">{design.esc(purpose)}. '
        f'Agent runs on this floor: {activity.get("total_runs", 0)}'
        + (f' | last: {design.esc(activity["last_run"])}' if activity.get("last_run") else "")
        + '</div></div>', unsafe_allow_html=True)


def _floor_logs(st, floor_no: int) -> None:
    with st.expander("Floor input/output history and errors"):
        events = building_service.floor_log(floor_no)
        if events:
            st.dataframe(pd.DataFrame(events), hide_index=True, use_container_width=True)
        else:
            st.caption("No activity recorded for this floor yet.")


def render_building_overview(st) -> None:
    st.title("\U0001F3DB Multibagger Scout AI - Trading Building")
    st.caption("Eight working floors over one orchestrator and one database. "
               "Connections pulse only while a floor has real activity in the last "
               f"{building_service.RECENT_MINUTES} minutes. Execution is simulated (paper) only.")
    activity = building_service.floor_activity()
    any_active = any(f.get("active") for f in activity.values())

    rows_html = []
    for no, name, icon, purpose in reversed(FLOORS):
        state = activity.get(no, {})
        cls = "floor active" if state.get("active") else "floor"
        rows_html.append(
            f'<div class="{cls}"><span class="fl-name">{icon} Floor {no:02d} - {name}</span>'
            f'<span class="fl-state">{"ACTIVE" if state.get("active") else "idle"}</span></div>')
    animation = (
        "@keyframes pulse{0%{opacity:.2}50%{opacity:1}100%{opacity:.2}}"
        ".wire{animation:pulse 1.2s infinite;background:#22c55e;}" if any_active else
        ".wire{background:#334155;}")
    rows_joined = ''.join(
        r + ('<div class="wire"></div>' if i < 7 else '')
        for i, r in enumerate(rows_html))
    html = (
        "<style>" + animation +
        ".bldg{max-width:640px;margin:0 auto;border:2px solid #334155;border-radius:10px;"
        "padding:10px;background:#0f172a;}"
        ".floor{display:flex;justify-content:space-between;padding:9px 14px;margin:4px 8px;"
        "border:1px solid #334155;border-radius:8px;color:#e2e8f0;background:#1e293b;}"
        ".floor.active{border-color:#22c55e;box-shadow:0 0 10px #22c55e66;}"
        ".fl-state{color:#94a3b8;font-size:.8rem;}"
        ".floor.active .fl-state{color:#22c55e;}"
        ".wire{width:4px;height:10px;margin:0 auto;}"
        "</style>"
        f'<div class="bldg">{rows_joined}</div>')
    st.markdown(html, unsafe_allow_html=True)
    if not any_active:
        st.caption("No floor has run in the last few minutes - connections are still. "
                   "Run research, a scan or a paper order and they light up.")

    st.subheader("Enter a floor")
    cols = st.columns(4)
    for index, (no, name, icon, _) in enumerate(FLOORS):
        if cols[index % 4].button(f"{icon} Floor {no:02d}\n{name}", key=f"enter-floor-{no}",
                                  use_container_width=True):
            st.query_params["page"] = FLOOR_PAGE_NAMES[no]
            st.rerun()

    st.divider()
    status = building_service.command_status()
    m = st.columns(4)
    m[0].metric("Universe instruments", status["companies"])
    m[1].metric("Agent runs (24h)", status["runs_24h"])
    m[2].metric("Open alerts", status["open_alerts"])
    m[3].metric("Paper orders", status["paper_orders"])


# ---------------------------------------------------------------- Floor 00

def render_floor00(st) -> None:
    _floor_chrome(st, 0)
    status = building_service.command_status()
    st.subheader("System health")
    cols = st.columns(4)
    cols[0].metric("Database", "OK" if status["database_ok"] else "ERROR")
    cols[1].metric("Agent runs (24h)", status["runs_24h"])
    cols[2].metric("Failed runs (24h)", status["failed_24h"])
    cols[3].metric("Open alerts", status["open_alerts"])

    st.subheader("Task queue (universe research)")
    queue = status["queue"] or {}
    if queue:
        st.dataframe(pd.DataFrame([{"research_status": k, "companies": v}
                                   for k, v in sorted(queue.items())]),
                     hide_index=True, use_container_width=True)
    else:
        st.caption("Universe not loaded on this hosted session yet - load it on Floor 01.")

    st.subheader("Data sources")
    if status["sources"]:
        st.dataframe(pd.DataFrame(status["sources"]), hide_index=True,
                     use_container_width=True)
    system.render_source_health(st)

    st.subheader("Global activity log")
    events = building_service.activity_log(30)
    if events:
        st.dataframe(pd.DataFrame(events), hide_index=True, use_container_width=True)
    else:
        st.caption("No activity yet on this hosted session.")


# ---------------------------------------------------------------- Floors 1-2

def render_floor01(st) -> None:
    _floor_chrome(st, 1)
    tab_scout, tab_nse, tab_bse = st.tabs(["Stock Scout", "NSE Screener", "BSE Screener"])
    with tab_scout:
        scouting.render_stock_scout(st)
    with tab_nse:
        scouting.render_nse_screener(st)
    with tab_bse:
        scouting.render_bse_screener(st)
    _floor_logs(st, 1)


def render_floor02(st) -> None:
    _floor_chrome(st, 2)
    dash_page.render(st)
    _floor_logs(st, 2)


# ---------------------------------------------------------------- Floor 03

def render_floor03(st) -> None:
    _floor_chrome(st, 3)
    st.caption("Risk verdicts here are research gates; they size SIMULATED positions only.")

    with session_scope() as session:
        researched = session.scalars(
            select(Company).where(Company.research_status.in_(["complete", "partial"]))
            .order_by(Company.symbol).limit(500)).all()
        options = [f"{c.symbol}:{c.exchange}" for c in researched]
    if not options:
        st.info("No researched companies on this hosted session yet - run research on Floor 02.")
    else:
        choice = st.selectbox("Company", options, key="risk-company")
        symbol, exchange = choice.split(":")
        view = dash_page.load_company(symbol, exchange)
        outputs = dash_page._latest_agent_outputs(view["company_id"]) if view.get("in_db") else {}
        risk = (outputs.get("risk_analysis") or {}).get("data") or {}
        if risk:
            st.markdown(f"**Classification:** {risk.get('classification', 'UNASSESSED')}")
            for finding in risk.get("findings", [])[:10]:
                st.markdown(f"- [{finding.get('severity')}] {finding.get('category')}: "
                            f"{finding.get('evidence')}")
            st.caption("Governance checks (pledging, auditors, related parties) are UNASSESSED - "
                       "no free verifiable source.")
        else:
            st.info("No risk analysis stored for this company yet.")

    st.subheader("Position sizing (simulated)")
    cash = paper_trading.virtual_cash()
    c1, c2, c3 = st.columns(3)
    risk_pct = c1.number_input("Risk per trade %", min_value=0.25, max_value=10.0,
                               value=1.0, step=0.25)
    entry = c2.number_input("Entry price", min_value=0.0, value=0.0, step=0.05)
    stop = c3.number_input("Stop-loss", min_value=0.0, value=0.0, step=0.05)
    if entry > 0 and 0 < stop < entry:
        risk_amount = cash * risk_pct / 100
        qty = int(risk_amount // (entry - stop))
        st.success(f"Virtual capital {cash:,.0f} | risk {risk_amount:,.0f} | "
                   f"per-share risk {entry - stop:,.2f} -> max size **{qty} shares** "
                   f"(cost {qty * entry:,.0f})")
    elif entry > 0:
        st.warning("Stop-loss must be below entry for a long position.")

    st.subheader("Paper portfolio exposure")
    summary = paper_trading.portfolio_summary()
    total = summary["cash"] + summary["invested"]
    invested_pct = (summary["invested"] / total * 100) if total else 0
    st.progress(min(invested_pct / 100, 1.0),
                text=f"Invested {summary['invested']:,.0f} of {total:,.0f} virtual "
                     f"({invested_pct:.1f}% exposure)")
    _floor_logs(st, 3)


# ---------------------------------------------------------------- Floor 04

def render_floor04(st) -> None:
    _floor_chrome(st, 4)
    st.warning("SIMULATED trading only. Orders fill at the latest free-feed close, "
               "which may be delayed. Nothing reaches a broker; no real money is involved.")
    with st.form("paper-order"):
        c1, c2, c3, c4 = st.columns(4)
        symbol = c1.text_input("Symbol", placeholder="RELIANCE")
        exchange = c2.selectbox("Exchange", ["NSE", "BSE"])
        side = c3.selectbox("Side", ["BUY", "SELL"])
        qty = c4.number_input("Qty", min_value=1, value=1)
        c5, c6 = st.columns(2)
        stop_loss = c5.number_input("Stop-loss (optional)", min_value=0.0, value=0.0, step=0.05)
        target = c6.number_input("Target (optional)", min_value=0.0, value=0.0, step=0.05)
        note = st.text_input("Note (optional)")
        if st.form_submit_button("Place SIMULATED order"):
            outcome = paper_trading.place_order(
                symbol, exchange, side, int(qty),
                stop_loss=stop_loss or None, target=target or None, note=note)
            if outcome.get("ok"):
                st.success(f"SIMULATED fill @ {outcome['fill_price']} "
                           f"(price as of {outcome['price_as_of']})")
            else:
                st.error(outcome.get("error"))

    st.subheader("Open simulated positions")
    summary = paper_trading.portfolio_summary()
    if summary["holdings"]:
        st.dataframe(pd.DataFrame(summary["holdings"]), hide_index=True,
                     use_container_width=True)
    else:
        st.caption("No open simulated positions.")
    st.subheader("Order history")
    history = paper_trading.trade_history()
    if history:
        st.dataframe(pd.DataFrame(history), hide_index=True, use_container_width=True)
    else:
        st.caption("No simulated orders yet.")
    with st.expander("Reset paper account"):
        st.caption("Deletes ALL simulated orders and restores the starting virtual cash. "
                   "Use this to clear test/demo activity.")
        confirm = st.checkbox("I want to wipe the simulated account", key="paper-reset-confirm")
        if st.button("Reset SIMULATED account", disabled=not confirm):
            result = paper_trading.reset_paper_account()
            st.success(f"Removed {result['deleted_orders']} simulated order(s); "
                       f"virtual cash restored to {result['cash']:,.0f}.")
            st.rerun()
    _floor_logs(st, 4)


# ---------------------------------------------------------------- Floor 05

def render_floor05(st) -> None:
    _floor_chrome(st, 5)
    tab_alerts, tab_news = st.tabs(["Alerts", "News monitor"])
    with tab_alerts:
        system.render_alerts(st)
    with tab_news:
        with session_scope() as session:
            rows = session.scalars(
                select(NewsArticle).order_by(desc(NewsArticle.published_at)).limit(40)).all()
        if rows:
            st.dataframe(pd.DataFrame([
                {"published": str(r.published_at)[:16] if r.published_at else "n/a",
                 "headline": r.headline, "source": r.source,
                 "sentiment": r.sentiment, "verification": r.verification_status}
                for r in rows]), hide_index=True, use_container_width=True)
            st.caption("Headlines are UNVERIFIED until a second source confirms them; "
                       "they are untrusted external content.")
        else:
            st.info("No headlines collected yet - news is gathered during research runs.")
    st.subheader("Stop-loss / target watch (simulated positions)")
    st.caption("Checked against the latest free-feed price ONLY while this page is open - "
               "there is no background monitor when the app is closed.")
    summary = paper_trading.portfolio_summary()
    watched = [h for h in summary["holdings"] if h["stop_loss"] or h["target"]]
    if not watched:
        st.caption("No simulated positions carry a stop-loss or target.")
    else:
        for h in watched:
            price = h["last_price"]
            flags = []
            if price and h["stop_loss"] and price <= h["stop_loss"]:
                flags.append(f"STOP-LOSS BREACHED (price {price:,.2f} <= SL {h['stop_loss']:,.2f})")
            if price and h["target"] and price >= h["target"]:
                flags.append(f"TARGET REACHED (price {price:,.2f} >= target {h['target']:,.2f})")
            if flags:
                st.error(f"{h['symbol']} ({h['exchange']}): " + "; ".join(flags))
            else:
                st.success(f"{h['symbol']} ({h['exchange']}): within band "
                           f"(last {price if price else 'n/a'}, SL {h['stop_loss'] or '-'}, "
                           f"target {h['target'] or '-'})")
    _floor_logs(st, 5)


# ---------------------------------------------------------------- Floor 06

def render_floor06(st) -> None:
    _floor_chrome(st, 6)
    summary = paper_trading.portfolio_summary()
    st.caption("All figures are SIMULATED (paper). Prices come from the free feed and may be delayed.")
    cols = st.columns(4)
    cols[0].metric("Virtual cash", f"{summary['cash']:,.0f}")
    cols[1].metric("Invested", f"{summary['invested']:,.0f}")
    cols[2].metric("Unrealised P&L", f"{summary['unrealised_pnl']:,.0f}")
    total = summary["cash"] + summary["invested"]
    pnl_pct = (summary["unrealised_pnl"] / summary["invested"] * 100) if summary["invested"] else 0
    cols[3].metric("Open P&L %", f"{pnl_pct:.2f}%")
    if summary["holdings"]:
        st.dataframe(pd.DataFrame(summary["holdings"]), hide_index=True,
                     use_container_width=True)
        invested = summary["invested"] or 1
        exposure = pd.DataFrame([
            {"symbol": h["symbol"], "exposure_%": round(h["value"] / (total or 1) * 100, 2)}
            for h in summary["holdings"]])
        st.subheader("Exposure by position")
        st.bar_chart(exposure.set_index("symbol"))
    else:
        st.info("No simulated holdings yet - place paper orders on Floor 04.")
    _floor_logs(st, 6)


# ---------------------------------------------------------------- Floor 07

def render_floor07(st) -> None:
    _floor_chrome(st, 7)
    st.caption("Consolidates stored research scores, ranks candidates and records a verdict "
               "with its rationale. Every verdict stays explainable via the score breakdown "
               "on Floor 02.")
    with session_scope() as session:
        rows = session.execute(
            select(Company.symbol, Company.exchange, ResearchScore.balanced_score,
                   ResearchScore.classification, ResearchScore.created_at)
            .join(ResearchScore, ResearchScore.company_id == Company.id)
            .order_by(desc(ResearchScore.created_at)).limit(200)).all()
    seen, ranked = set(), []
    for symbol, exchange, score, classification, created in rows:
        if (symbol, exchange) in seen:
            continue
        seen.add((symbol, exchange))
        ranked.append({"symbol": symbol, "exchange": exchange,
                       "balanced_score": round(score, 1) if score is not None else None,
                       "labels": classification, "scored": str(created)[:16]})
    if ranked:
        ranked.sort(key=lambda r: (r["balanced_score"] is not None, r["balanced_score"] or 0),
                    reverse=True)
        st.dataframe(pd.DataFrame(ranked[:30]), hide_index=True, use_container_width=True)

        with st.form("decision-form"):
            choice = st.selectbox("Verdict for", [f"{r['symbol']}:{r['exchange']}" for r in ranked[:30]])
            verdict = st.radio("Verdict", ["approved", "watchlist", "paper_trade", "rejected"],
                               horizontal=True)
            rationale = st.text_input("Rationale (what the scores showed)")
            if st.form_submit_button("Record verdict"):
                symbol, exchange = choice.split(":")
                view = dash_page.load_company(symbol, exchange)
                score = (view.get("scores") or {}).get("balanced")
                with session_scope() as session:
                    session.add(Decision(
                        company_id=view.get("company_id"), symbol=symbol, verdict=verdict,
                        rationale=rationale[:1000], balanced_score=score))
                extra = ""
                if verdict == "watchlist":
                    outcome = wl_service.add_symbol(symbol, exchange)
                    extra = " (watchlist updated)" if outcome.get("ok") else f" ({outcome.get('error')})"
                elif verdict == "paper_trade":
                    extra = " - place the simulated order on Floor 04"
                st.success(f"Verdict recorded: {verdict} for {symbol}{extra}")
    else:
        st.info("No scored companies yet - run research on Floor 02.")

    with session_scope() as session:
        decisions = session.scalars(
            select(Decision).order_by(desc(Decision.created_at)).limit(20)).all()
    if decisions:
        st.subheader("Decision log")
        st.dataframe(pd.DataFrame([
            {"when": str(d.created_at)[:16], "symbol": d.symbol, "verdict": d.verdict,
             "score": d.balanced_score, "rationale": d.rationale[:120]}
            for d in decisions]), hide_index=True, use_container_width=True)
    _floor_logs(st, 7)
