"""Dashboard page matching the user's reference layout.

Pipeline panel, company strip, 11 research tabs, score rings, EMA chart,
company snapshot, insights, thesis and news. Every number comes from the
local research database, committed rotation snapshots, or a live free
connector fetch; missing data is shown as n/a, never invented.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pandas as pd
import streamlit as st
from sqlalchemy import desc, func, select

from database.connection import session_scope
from database.models import (
    AgentOutput, AgentRun, Company, MarketPrice, NewsArticle,
    ResearchReport, ResearchScore, Watchlist, WatchlistItem,
)
from frontend import design
from services.snapshots import get_snapshot

AGENT_STAGES = [
    ("scout", "Stock Scout", None),            # collection stage, no AgentRun row
    ("fundamental", "Fundamental", "fundamental_analysis"),
    ("technical", "Technical", "technical_analysis"),
    ("business", "Business", "business_quality"),
    ("valuation", "Valuation", "valuation"),
    ("risk", "Risk", "risk_analysis"),
    ("news", "News", "news_intelligence"),
    ("scoring", "Scoring", "scoring"),
]

TAB_NAMES = ["Overview", "Fundamentals", "Financials", "Technical", "Business",
             "Valuation", "Risk", "News", "AI Report", "Charts", "History"]

GOVERNANCE_NOTE = (
    "Governance checks (share pledging, auditor changes, related-party deals, "
    "regulatory actions) are UNASSESSED: no free verifiable source."
)


# ---------------------------------------------------------------- data layer

@st.cache_data(ttl=3600, show_spinner=False)
def universe_frame() -> pd.DataFrame:
    from scripts.daily_update import load_universe
    return pd.DataFrame(load_universe())


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def fetch_history(symbol: str, exchange: str, period: str = "1y") -> pd.DataFrame:
    """Live free-connector fetch for companies not researched this session."""
    from data.connectors.yfinance_connector import YFinanceConnector
    result = YFinanceConnector().get_history(symbol, exchange, period=period, interval="1d")
    if not result.ok:
        return pd.DataFrame()
    frame = result.data["frame"].copy()
    frame.index = pd.to_datetime(frame.index)
    return frame


def _latest_agent_outputs(company_id: int) -> dict[str, dict]:
    outputs: dict[str, dict] = {}
    with session_scope() as session:
        rows = session.execute(
            select(AgentRun.agent_name, AgentRun.status, AgentRun.finished_at,
                   AgentOutput.output_json)
            .join(AgentOutput, AgentOutput.run_id == AgentRun.id)
            .where(AgentOutput.company_id == company_id)
            .order_by(desc(AgentOutput.created_at))
        ).all()
    for agent_name, status, finished_at, payload in rows:
        if agent_name in outputs:
            continue
        try:
            data = json.loads(payload or "{}")
        except ValueError:
            data = {}
        outputs[agent_name] = {"run_status": status, "finished_at": finished_at, **data}
    return outputs


def load_company(symbol: str, exchange: str) -> dict:
    symbol = symbol.strip().upper()
    view: dict = {"symbol": symbol, "exchange": exchange, "in_db": False,
                  "company_id": None, "name": None, "snapshot": get_snapshot(symbol, exchange)}
    with session_scope() as session:
        company = session.scalar(
            select(Company).where(Company.symbol == symbol, Company.exchange == exchange))
        if company is not None:
            view.update(in_db=True, company_id=company.id, name=company.name,
                        sector=company.sector, industry=company.industry,
                        market_cap=company.market_cap,
                        research_status=company.research_status)
            score = session.scalar(
                select(ResearchScore).where(ResearchScore.company_id == company.id)
                .order_by(desc(ResearchScore.created_at)).limit(1))
            if score is not None:
                view["scores"] = {
                    "fundamental": score.fundamental_score, "technical": score.technical_score,
                    "data_confidence": score.data_confidence, "risk": score.risk_score,
                    "long_term": score.long_term_score, "short_term": score.short_term_score,
                    "balanced": score.balanced_score,
                }
                view["classification"] = score.classification
                try:
                    view["explanation"] = json.loads(score.explanation_json or "{}")
                except ValueError:
                    view["explanation"] = {}
                view["score_date"] = str(score.created_at)[:16]
            price_stats = session.execute(
                select(func.count(MarketPrice.id), func.max(MarketPrice.ts))
                .where(MarketPrice.company_id == company.id, MarketPrice.interval == "1d")).first()
            view["price_rows"] = price_stats[0] or 0
    if view["name"] is None and view.get("snapshot"):
        view["name"] = view["snapshot"].get("name")
    if view["name"] is None:
        uni = universe_frame()
        match = uni[uni["symbol"].str.upper() == symbol]
        view["name"] = match.iloc[0]["name"] if not match.empty else symbol
    if "scores" not in view and view.get("snapshot"):
        snap = view["snapshot"]
        view["scores"] = snap.get("scores")
        view["classification"] = snap.get("classification")
        view["explanation"] = snap.get("explanation") or {}
        view["score_date"] = snap.get("updated_at")
        view["snapshot_only"] = True
    view.setdefault("snapshot_only", False)
    return view


def price_history(view: dict) -> tuple[pd.DataFrame, str]:
    """(frame, source label). DB first, else a live connector fetch."""
    if view.get("in_db") and view.get("price_rows"):
        from frontend import components
        frame = components.price_frame(view["company_id"], limit=1300)
        if not frame.empty:
            return frame, "stored research data"
    frame = fetch_history(view["symbol"], view["exchange"])
    return frame, "live free feed (yfinance), not stored"


# ---------------------------------------------------------------- chart

def ema_chart(frame: pd.DataFrame, title: str, height: int = 460) -> "object":
    import plotly.graph_objects as go
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=frame.index, open=frame["open"], high=frame["high"],
        low=frame["low"], close=frame["close"], name="Price",
        increasing_line_color="#00d09c", decreasing_line_color="#ef4444"))
    close = frame["close"]
    for span, color in ((20, "#2f7bff"), (50, "#f59e0b"), (200, "#a855f7")):
        if len(frame) >= span:
            fig.add_trace(go.Scatter(x=frame.index, y=close.ewm(span=span, adjust=False).mean(),
                                     name=f"EMA {span}", line=dict(width=1.4, color=color)))
    fig.add_trace(go.Bar(x=frame.index, y=frame["volume"], name="Volume",
                         marker_color="rgba(47,123,255,0.25)", yaxis="y2"))
    fig.update_layout(
        title=dict(text=title, font=dict(size=14, color="#b9c6dd")),
        template="plotly_dark", paper_bgcolor="#101a33", plot_bgcolor="#101a33",
        height=height, margin=dict(l=10, r=10, t=36, b=10),
        legend=dict(orientation="h", y=1.06, font=dict(size=11)),
        xaxis=dict(rangeslider=dict(visible=False),
                   rangeselector=dict(
                       buttons=[dict(count=1, label="1M", step="month", stepmode="backward"),
                                dict(count=3, label="3M", step="month", stepmode="backward"),
                                dict(count=6, label="6M", step="month", stepmode="backward"),
                                dict(count=1, label="1Y", step="year", stepmode="backward"),
                                dict(count=3, label="3Y", step="year", stepmode="backward"),
                                dict(count=5, label="5Y", step="year", stepmode="backward")],
                       bgcolor="#0e1830", font=dict(color="#b9c6dd"))),
        yaxis=dict(title=None),
        yaxis2=dict(overlaying="y", side="right", showgrid=False, visible=False),
    )
    return fig


# ---------------------------------------------------------------- panels

def pipeline_statuses(view: dict) -> tuple[list[dict], int]:
    stages = []
    done = 0
    outputs = _latest_agent_outputs(view["company_id"]) if view.get("in_db") else {}
    for key, name, agent_name in AGENT_STAGES:
        if agent_name is None:
            has = view.get("in_db") and view.get("price_rows")
            status = "done" if has else "pending"
        else:
            run = (outputs.get(agent_name) or {}).get("run_status")
            status = {"success": "done", "partial": "partial", "failed": "failed"}.get(run, "pending")
        done += status == "done"
        stages.append({"key": key, "name": name + " Agent" if key != "scout" else "Stock Scout",
                       "icon": design.ICONS.get(key, ""), "status": status})
    return stages, done


def render_pipeline(st, view: dict) -> None:
    stages, done = pipeline_statuses(view)
    pct = round(100 * done / len(stages))
    if view.get("snapshot_only"):
        st.caption(
            "This stock was refreshed by the hosted daily rotation on "
            f"{view.get('score_date') or 'unknown date'}; the full eight-agent pipeline has not run "
            "on this hosted session yet. Run full research to populate every stage.")
    cols = st.columns([5, 1])
    with cols[0]:
        st.markdown(
            f'<div class="mb-card"><h4>\U0001F916 AI Research Pipeline - {design.esc(view["name"])}</h4>'
            + design.pipeline_html(stages) + "</div>", unsafe_allow_html=True)
    with cols[1]:
        st.markdown(f'<div class="mb-card" style="text-align:center;">'
                    + design.progress_ring_svg(pct) + "</div>", unsafe_allow_html=True)


def render_strip(st, view: dict, frame: pd.DataFrame, source: str) -> None:
    name = view["name"]
    symbol, exchange = view["symbol"], view["exchange"]
    chips = [f"{exchange}: {symbol}"]
    if exchange == "NSE":
        chips.append("BSE: n/a")
    if view.get("sector"):
        chips.append(view["sector"])
    cap = view.get("market_cap")
    cap_txt = f"Market Cap: ₹{cap / 1e7:,.1f} Cr" if cap else "Market Cap: n/a"

    price_txt, chg_html, ts_txt = "n/a", "", "no price data"
    if not frame.empty:
        last = frame.iloc[-1]
        price = float(last["close"])
        price_txt = f"₹{price:,.2f}"
        ts_txt = f"As on {frame.index[-1].strftime('%d %b %Y')} ({source})"
        if len(frame) >= 2:
            prev = float(frame["close"].iloc[-2])
            chg = price - prev
            pct = chg / prev * 100 if prev else 0.0
            cls = "mb-up" if chg >= 0 else "mb-down"
            arrow = "\u25B2" if chg >= 0 else "\u25BC"
            chg_html = f'<div class="{cls}">{arrow} {chg:+,.2f} ({pct:+.2f}%)</div>'

    initial = (name or symbol)[:1].upper()
    cols = st.columns([3, 2])
    with cols[0]:
        st.markdown(
            f'<div class="mb-card" style="display:flex;gap:16px;align-items:center;">'
            f'<div style="width:64px;height:64px;border-radius:12px;background:#0e1830;border:1px solid var(--border);'
            f'display:flex;align-items:center;justify-content:center;font-size:1.7rem;font-weight:800;color:#7fb0ff;">{design.esc(initial)}</div>'
            f'<div><div style="font-size:1.35rem;font-weight:800;">{design.esc(name)}</div>'
            f'<div style="margin:6px 0;">' + "".join(f'<span class="mb-chip">{design.esc(c)}</span>' for c in chips)
            + "</div>"
            f'<div class="muted" style="font-size:0.85rem;">{design.esc(view.get("industry") or "Industry: n/a")} | {design.esc(cap_txt)}</div>'
            "</div></div>", unsafe_allow_html=True)
    with cols[1]:
        st.markdown(
            f'<div class="mb-card" style="text-align:right;"><div class="mb-price">{price_txt}</div>'
            f'{chg_html}<div class="muted" style="font-size:0.78rem;">{design.esc(ts_txt)}</div></div>',
            unsafe_allow_html=True)
    bcols = st.columns([1, 1.4, 1])
    with bcols[0]:
        watchlisted = _is_watchlisted(view.get("company_id"))
        if st.button("\u2B50 Watchlist" if not watchlisted else "\u2713 Watchlisted",
                           key="strip-watch", disabled=not view.get("in_db"),
                           help=None if view.get("in_db") else "Run full research first"):
            _toggle_watchlist(view)
            st.rerun()
    with bcols[1]:
        if st.button("\U0001F504 Run full research", key="strip-research", use_container_width=True):
            _run_research(view)
    with bcols[2]:
        if st.button("\U0001F4C4 Export report", key="strip-export",
                           disabled=not _has_reports(view.get("company_id")),
                           help=None if _has_reports(view.get("company_id"))
                           else "Reports exist after a full research run"):
            st.session_state["ms_goto_tab"] = "AI Report"


def _is_watchlisted(company_id: int | None) -> bool:
    if company_id is None:
        return False
    with session_scope() as session:
        return session.scalar(
            select(func.count(WatchlistItem.id)).where(WatchlistItem.company_id == company_id)) > 0


def _toggle_watchlist(view: dict) -> None:
    with session_scope() as session:
        wl = session.scalar(select(Watchlist).where(Watchlist.name == "My Watchlist"))
        if wl is None:
            wl = Watchlist(name="My Watchlist", kind="custom")
            session.add(wl)
            session.flush()
        item = session.scalar(
            select(WatchlistItem).where(WatchlistItem.watchlist_id == wl.id,
                                        WatchlistItem.company_id == view["company_id"]))
        if item is None:
            session.add(WatchlistItem(watchlist_id=wl.id, company_id=view["company_id"]))
        else:
            session.delete(item)


def _has_reports(company_id: int | None) -> bool:
    if company_id is None:
        return False
    with session_scope() as session:
        return session.scalar(
            select(func.count(ResearchReport.id)).where(ResearchReport.company_id == company_id)) > 0


def _run_research(view: dict) -> None:
    from engine.orchestrator import research_company
    with st.spinner(f"Running all eight agents on {view['symbol']}... this takes a minute on free data sources."):
        outcome = research_company(view["symbol"], view["exchange"])
    st.session_state["ms_last_run"] = outcome
    st.rerun()


def render_overview(st, view: dict, frame: pd.DataFrame, source: str) -> None:
    scores = view.get("scores") or {}
    classification = view.get("classification")
    left, right = st.columns([2, 1])
    with left:
        risk_score = scores.get("risk")
        risk_sub = "higher = more risk"
        if risk_score is not None and risk_score <= 5:
            risk_sub = "no quant red flags found; governance unassessed"
        rings = (
            '<div style="display:flex;gap:10px;justify-content:space-around;flex-wrap:wrap;">'
            + design.ring_svg(scores.get("fundamental"), "Fundamental", "higher is stronger", "#00d09c")
            + design.ring_svg(scores.get("technical"), "Technical", "higher is stronger", "#2f7bff")
            + design.ring_svg(scores.get("data_confidence"), "Data Confidence", "coverage quality", "#a855f7")
            + design.ring_svg(risk_score, "Risk Score", risk_sub, "#f59e0b")
            + "</div>"
        )
        balanced = scores.get("balanced")
        if balanced is not None:
            cls = {"high_risk": "risk"}.get(classification or "", "")
            if not cls and balanced < 40:
                cls = "warn"
            banner = (
                f'<div class="mb-overall {cls}">\u2B50 Overall Score: {balanced:.1f} / 100'
                f'<span class="sub">{design.esc((classification or "unclassified").replace("_", " ").title())} | '
                "Overall = 0.5 x long-term + 0.5 x short-term "
                "(long-term = 0.7 x fundamental + 0.3 x technical; short-term swapped). "
                f"Scores from {design.esc(view.get('score_date') or 'unknown date')}. "
                + GOVERNANCE_NOTE + "</span></div>"
            )
        else:
            banner = ('<div class="mb-overall warn">No scores yet'
                      '<span class="sub">Run full research or wait for this stock\'s rotation refresh.</span></div>')
        st.markdown('<div class="mb-card"><h4>\U0001F3C6 Research Scores</h4>' + rings
                    + '<div style="height:10px;"></div>' + banner + "</div>", unsafe_allow_html=True)
    with right:
        rows = [("Sector", view.get("sector") or "n/a"),
                ("Industry", view.get("industry") or "n/a")]
        if not frame.empty:
            window = frame.tail(250)
            rows += [("52 Week High", f"₹{float(window['high'].max()):,.2f}"),
                     ("52 Week Low", f"₹{float(window['low'].min()):,.2f}")]
        outputs = _latest_agent_outputs(view["company_id"]) if view.get("in_db") else {}
        fund = (outputs.get("fundamental_analysis") or {}).get("data") or {}
        val = (outputs.get("valuation") or {}).get("data") or {}
        multiples = val.get("multiples") or {}
        prof = fund.get("profitability") or {}
        bs = fund.get("balance_sheet") or {}
        rows += [
            ("PE Ratio", f"{multiples['pe_trailing']:.1f}" if multiples.get("pe_trailing") else "n/a"),
            ("Dividend Yield", f"{multiples['dividend_yield']:.1f}%" if multiples.get("dividend_yield") is not None else "n/a"),
            ("ROE", f"{prof['roe'] * 100:.1f}%" if isinstance(prof.get("roe"), (int, float)) else "n/a"),
            ("Debt/Equity", f"{bs['debt_to_equity']:.2f}" if isinstance(bs.get("debt_to_equity"), (int, float)) else "n/a"),
        ]
        st.markdown('<div class="mb-card"><h4>\u2139\uFE0F Company Snapshot</h4>'
                    + design.kv(rows) + "</div>", unsafe_allow_html=True)

    if not frame.empty:
        st.plotly_chart(ema_chart(frame, f"Price Chart - {view['symbol']} ({source})"),
                        use_container_width=True)
    else:
        st.info("No price history available from free sources for this stock yet.")

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown('<div class="mb-card"><h4>\U0001F4A1 Key Insights</h4>'
                    + _insights_html(view) + "</div>", unsafe_allow_html=True)
    with c2:
        st.markdown('<div class="mb-card"><h4>\U0001F3AF Investment Thesis</h4>'
                    + _thesis_html(view) + "</div>", unsafe_allow_html=True)
    with c3:
        st.markdown('<div class="mb-card"><h4>\U0001F4F0 Latest News</h4>'
                    + _news_html(view) + "</div>", unsafe_allow_html=True)


def _insights_html(view: dict) -> str:
    outputs = _latest_agent_outputs(view["company_id"]) if view.get("in_db") else {}
    items: list[tuple[str, str]] = []  # (kind, text) kind: ok|warn
    biz = (outputs.get("business_quality") or {}).get("data") or {}
    for ev in (biz.get("evidence") or [])[:6]:
        if isinstance(ev, dict):
            kind = "ok" if ev.get("direction") == "positive" else "warn"
            items.append((kind, str(ev.get("point") or ev.get("text") or "")[:140]))
        else:
            items.append(("ok", str(ev)[:140]))
    risk = (outputs.get("risk_analysis") or {}).get("data") or {}
    for finding in (risk.get("findings") or [])[:3]:
        items.append(("warn", str(finding)[:140]))
    if not items and view.get("explanation"):
        # rotation-snapshot path: strongest and weakest scoring groups
        groups = []
        for agent, sections in view["explanation"].items():
            if not isinstance(sections, dict):
                continue
            for name, detail in sections.items():
                if isinstance(detail, dict) and detail.get("max"):
                    groups.append((detail.get("points", 0) / detail["max"], agent, name, detail))
        groups.sort(reverse=True)
        for ratio, agent, name, detail in groups[:2]:
            items.append(("ok", f"{agent}: strong {name.replace('_', ' ')} ({detail.get('points')}/{detail.get('max')})"))
        for ratio, agent, name, detail in groups[-2:]:
            if ratio < 0.45:
                items.append(("warn", f"{agent}: weak {name.replace('_', ' ')} ({detail.get('points')}/{detail.get('max')})"))
    if not items:
        return '<div class="muted">Insights appear after research data exists for this company.</div>'
    lis = "".join(
        f'<li class="{ "warn" if kind == "warn" else "" }">{design.esc(text)}</li>'
        for kind, text in items[:5])
    return f'<ul class="mb-ins">{lis}</ul>'


def _thesis_html(view: dict) -> str:
    outputs = _latest_agent_outputs(view["company_id"]) if view.get("in_db") else {}
    biz = (outputs.get("business_quality") or {}).get("data") or {}
    val = (outputs.get("valuation") or {}).get("data") or {}
    parts = []
    if biz.get("moat_assessment"):
        parts.append(str(biz["moat_assessment"])[:220])
    elif biz.get("classification"):
        parts.append(f"Business quality: {str(biz['classification']).replace('_', ' ')}.")
    if val.get("margin_of_safety_vs_base_case") is not None:
        mos = val["margin_of_safety_vs_base_case"]
        if isinstance(mos, (int, float)):
            parts.append(f"Margin of safety vs base case: {mos:+.1%}.")
    scores = view.get("scores") or {}
    if scores.get("data_confidence") is not None:
        parts.append(f"Research confidence {scores['data_confidence']:.0f}/100.")
    if not parts:
        return ('<div class="muted">The thesis is composed from the business and valuation agents. '
                "Run full research to generate it.</div>")
    return '<div style="font-size:0.9rem;">' + design.esc(" ".join(parts)) + "</div>"


def _news_html(view: dict) -> str:
    if not view.get("in_db"):
        return '<div class="muted">News is stored after a full research run (free RSS feeds).</div>'
    with session_scope() as session:
        rows = session.scalars(
            select(NewsArticle).where(NewsArticle.company_id == view["company_id"])
            .order_by(desc(NewsArticle.published_at)).limit(5)).all()
    if not rows:
        return '<div class="muted">No news items stored for this company yet.</div>'
    items = "".join(
        f'<div style="padding:5px 0;border-bottom:1px dashed #1a2742;">'
        f'<div style="font-size:0.88rem;">{design.esc(r.headline[:110])}</div>'
        f'<div class="muted" style="font-size:0.72rem;">{design.esc(r.source)} | '
        f'{design.esc(str(r.published_at)[:10] if r.published_at else "date n/a")} | '
        f'{design.esc(r.sentiment)}</div></div>'
        for r in rows)
    return items


# ---------------------------------------------------------------- other tabs

def _agent_tab(st, view: dict, agent_name: str, title: str, renderer) -> None:
    if not view.get("in_db"):
        _empty_state(st, view, title)
        return
    outputs = _latest_agent_outputs(view["company_id"])
    output = outputs.get(agent_name)
    if not output:
        _empty_state(st, view, title)
        return
    st.caption(f"Source agent: {agent_name} | run status: {output.get('run_status')} | "
               f"finished: {output.get('finished_at') or 'n/a'}")
    data = output.get("data") or {}
    if output.get("missing"):
        st.caption("Missing/unavailable: " + ", ".join(str(m) for m in output["missing"][:10]))
    renderer(st, data)


def _empty_state(st, view: dict, title: str) -> None:
    if view.get("snapshot_only"):
        st.info(f"{title}: not collected by the daily rotation (scores only). "
                "Run full research to populate this tab.")
    else:
        st.info(f"{title}: no data yet.")
    if st.button(f"\U0001F504 Run full research for {view['symbol']}", key=f"run-{title}"):
        _run_research(view)


def _table_from_dict(st, data: dict, key_name: str = "metric") -> None:
    rows = [{"metric": k, "value": (f"{v:.4g}" if isinstance(v, float) else v)}
            for k, v in data.items() if not isinstance(v, (dict, list))]
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


def render_tabs(st, view: dict, frame: pd.DataFrame, source: str) -> None:
    tabs = st.tabs(TAB_NAMES)

    with tabs[0]:
        render_overview(st, view, frame, source)

    with tabs[1]:  # Fundamentals
        def _fund(st, data):
            for group, title in (("growth", "Growth"), ("profitability", "Profitability"),
                                 ("balance_sheet", "Balance sheet"), ("cash_flow", "Cash flow"),
                                 ("ownership", "Ownership")):
                st.markdown(f"**{title}**")
                _table_from_dict(st, data.get(group) or {})
            if data.get("red_flags"):
                st.error("Red flags: " + "; ".join(str(f) for f in data["red_flags"]))
        _agent_tab(st, view, "fundamental_analysis", "Fundamentals", _fund)

    with tabs[2]:  # Financials
        def _fin(st, data):
            statements = data.get("statements") or {}
            annual = statements.get("annual") or {}
            quarterly = statements.get("quarterly") or {}
            if not annual and not quarterly:
                st.info("No financial statements stored.")
                return
            for label, block in (("Annual", annual), ("Quarterly", quarterly)):
                if not block:
                    continue
                st.markdown(f"**{label} statements** (periods: {', '.join((data.get('annual_periods') or [])[:4]) if label == 'Annual' else ', '.join((data.get('quarterly_periods') or [])[:4])})")
                st.dataframe(pd.DataFrame(block), use_container_width=True)
        _agent_tab(st, view, "fundamental_analysis", "Financials", _fin)

    with tabs[3]:  # Technical
        def _tech(st, data):
            st.markdown(f"**Assessment:** {data.get('assessment', 'n/a')}")
            daily = data.get("daily") or {}
            cols = st.columns(4)
            for col, (label, key, fmt) in zip(cols, (
                    ("RSI(14)", "rsi_14", "{:.1f}"), ("ADX(14)", "adx_14", "{:.1f}"),
                    ("ATR(14)", "atr_14", "{:.2f}"), ("Rel. volume", "relative_volume", "{:.2f}x"))):
                value = daily.get(key)
                col.metric(label, fmt.format(value) if isinstance(value, (int, float)) else "n/a")
            _table_from_dict(st, daily)
            for report_key in ("short_term_report", "long_term_report"):
                if data.get(report_key):
                    st.markdown(f"**{report_key.replace('_', ' ').title()}:** {data[report_key]}")
        _agent_tab(st, view, "technical_analysis", "Technical", _tech)

    with tabs[4]:  # Business
        def _biz(st, data):
            st.markdown(f"**Classification:** {str(data.get('classification', 'n/a')).replace('_', ' ')}")
            if data.get("moat_assessment"):
                st.markdown(f"**Moat:** {data['moat_assessment']}")
            if data.get("evidence"):
                st.markdown("**Evidence**")
                for ev in data["evidence"][:10]:
                    st.caption(str(ev)[:200])
            if data.get("unassessed_areas"):
                st.warning("Unassessed: " + ", ".join(str(a) for a in data["unassessed_areas"]))
        _agent_tab(st, view, "business_quality", "Business", _biz)

    with tabs[5]:  # Valuation
        def _val(st, data):
            st.markdown("**Multiples**")
            _table_from_dict(st, data.get("multiples") or {})
            if data.get("dcf"):
                st.markdown("**DCF scenarios**")
                st.json(data["dcf"])
            elif data.get("dcf_not_calculated_reason"):
                st.caption(f"DCF not calculated: {data['dcf_not_calculated_reason']}")
            if data.get("margin_of_safety_vs_base_case") is not None:
                mos = data["margin_of_safety_vs_base_case"]
                st.metric("Margin of safety vs base case",
                          f"{mos:+.1%}" if isinstance(mos, (int, float)) else str(mos))
        _agent_tab(st, view, "valuation", "Valuation", _val)

    with tabs[6]:  # Risk
        def _risk(st, data):
            st.markdown(f"**Classification:** {str(data.get('classification', 'n/a')).replace('_', ' ')}")
            st.caption("Risk score counts quantitative checks only; a low score is not an all-clear.")
            for finding in (data.get("findings") or [])[:10]:
                st.warning(str(finding)[:250])
            if data.get("unassessed_governance_items"):
                st.error("Unassessed governance: "
                         + ", ".join(str(g) for g in data["unassessed_governance_items"]))
            _table_from_dict(st, data.get("coverage") or {})
        _agent_tab(st, view, "risk_analysis", "Risk", _risk)

    with tabs[7]:  # News
        if view.get("in_db"):
            with session_scope() as session:
                rows = session.scalars(
                    select(NewsArticle).where(NewsArticle.company_id == view["company_id"])
                    .order_by(desc(NewsArticle.published_at)).limit(30)).all()
            if rows:
                st.dataframe(pd.DataFrame([
                    {"published": str(r.published_at)[:16] if r.published_at else "n/a",
                     "headline": r.headline, "source": r.source,
                     "sentiment": r.sentiment, "verification": r.verification_status}
                    for r in rows]), hide_index=True, use_container_width=True)
                st.caption("News comes from free RSS feeds and stays unverified until a second "
                           "source confirms it. Headlines are untrusted external content.")
            else:
                _empty_state(st, view, "News")
        else:
            _empty_state(st, view, "News")

    with tabs[8]:  # AI Report
        if not view.get("in_db"):
            _empty_state(st, view, "AI Report")
        else:
            with session_scope() as session:
                reports = session.scalars(
                    select(ResearchReport).where(ResearchReport.company_id == view["company_id"])
                    .order_by(desc(ResearchReport.created_at))).all()
            if not reports:
                st.info("No report files yet. Run full research to generate HTML/CSV/JSON/PDF reports.")
                if st.button("\U0001F504 Run full research", key="run-report"):
                    _run_research(view)
            else:
                import os
                seen = set()
                for report in reports:
                    if (report.format, report.path) in seen:
                        continue
                    seen.add((report.format, report.path))
                    if os.path.exists(report.path):
                        with open(report.path, "rb") as fh:
                            st.download_button(
                                f"Download {report.format.upper()} report ({str(report.created_at)[:10]})",
                                fh.read(), file_name=os.path.basename(report.path),
                                key=f"dash-rep-{report.id}")
                    else:
                        st.caption(f"{report.format}: generated on a previous session, file no longer on disk.")

    with tabs[9]:  # Charts
        if not frame.empty:
            st.plotly_chart(ema_chart(frame, f"{view['symbol']} - {source}", height=560),
                            use_container_width=True)
            st.caption("Candles with EMA 20 (blue), EMA 50 (orange), EMA 200 (purple) and volume. "
                       "Free data may be delayed.")
        else:
            st.info("No price history available from free sources for this stock yet.")

    with tabs[10]:  # History
        if view.get("in_db"):
            with session_scope() as session:
                rows = session.execute(
                    select(AgentRun.agent_name, AgentRun.status, AgentRun.started_at,
                           AgentRun.finished_at, AgentRun.error)
                    .join(AgentOutput, AgentOutput.run_id == AgentRun.id)
                    .where(AgentOutput.company_id == view["company_id"])
                    .order_by(desc(AgentRun.id)).limit(40)).all()
            if rows:
                st.dataframe(pd.DataFrame([
                    {"agent": r[0], "status": r[1], "started": str(r[2])[:16],
                     "finished": str(r[3])[:16] if r[3] else "-",
                     "error": (r[4] or "")[:100]} for r in rows]),
                    hide_index=True, use_container_width=True)
            else:
                st.info("No agent runs recorded for this company yet.")
        else:
            _empty_state(st, view, "History")


# ---------------------------------------------------------------- search + entry

def company_search(st, key: str = "dash-search") -> None:
    uni = universe_frame()
    query = st.text_input("Search company (name or symbol)", key=key,
                          placeholder="e.g. TCS, Reliance, 20MICRONS")
    if not query:
        return
    query_up = query.strip().upper()
    mask = uni["symbol"].str.upper().str.contains(query_up, regex=False) | \
        uni["name"].str.upper().str.contains(query_up, regex=False)
    matches = uni[mask].head(25)
    if matches.empty:
        st.caption("No NSE-universe match. BSE symbols can still be run from Stock Scout.")
        return
    options = {f"{r['name']} ({r['symbol']})": r["symbol"] for _, r in matches.iterrows()}
    picked = st.selectbox("Matches", list(options), key=f"{key}-pick")
    if st.button("Open company", key=f"{key}-open"):
        st.session_state["ms_symbol"] = options[picked]
        st.session_state["ms_exchange"] = "NSE"
        st.rerun()


def default_symbol() -> str | None:
    from frontend import components
    scores = components.latest_scores()
    if scores.empty:
        return None
    top = scores.drop_duplicates("symbol").sort_values("balanced", ascending=False).iloc[0]
    return top["symbol"]


def render(st) -> None:
    symbol = st.session_state.get("ms_symbol")
    if not symbol:
        symbol = default_symbol()
    if not symbol:
        st.info("No researched or rotation-refreshed stock yet. Search below or wait for the daily rotation.")
        company_search(st)
        return
    exchange = st.session_state.get("ms_exchange", "NSE")

    view = load_company(symbol, exchange)
    outcome = st.session_state.pop("ms_last_run", None)
    if outcome:
        statuses = outcome.get("agent_statuses") or {}
        st.success(f"Research finished: {outcome.get('status')} | "
                   + ", ".join(f"{k}: {v}" for k, v in statuses.items()))

    with st.expander("\U0001F50E Search / switch company", expanded=False):
        company_search(st)

    frame, source = price_history(view)
    render_pipeline(st, view)
    render_strip(st, view, frame, source)
    render_tabs(st, view, frame, source)
