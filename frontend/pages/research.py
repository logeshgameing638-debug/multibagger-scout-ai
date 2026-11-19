"""Pages 5-10: Fundamental, Technical, Business, Valuation, Risk, News."""
from __future__ import annotations

import pandas as pd

from frontend import components


def _pick_company(st, key: str) -> int | None:
    options = components.company_options()
    if not options:
        st.info("No companies researched yet. Run a scan from Stock Scout.")
        return None
    labels = [label for label, _ in options]
    choice = st.selectbox("Company", labels, key=key)
    return dict(options)[choice]


def _show_agent(st, company_id: int, agent: str, title: str) -> dict | None:
    output = components.latest_agent_output(company_id, agent)
    st.caption(f"Source agent: {agent} | status: {(output or {}).get('status', 'no run yet')}")
    if output is None:
        st.warning(f"No {title} data for this company yet - run research first.")
        return None
    if output.get("missing"):
        st.caption("Missing/unavailable: " + ", ".join(str(m) for m in output["missing"][:12]))
    if output.get("warnings"):
        with st.expander("Warnings"):
            for warning in output["warnings"][:5]:
                st.caption(str(warning)[:300])
    return output


def render_fundamental(st) -> None:
    st.title("Fundamental Analysis")
    company_id = _pick_company(st, "fund")
    if company_id is None:
        return
    output = _show_agent(st, company_id, "fundamental_analysis", "fundamental")
    if not output:
        return
    data = output["data"]
    if data.get("is_financial_sector"):
        st.info("Financial-sector company: industrial debt/current-ratio rules not applied.")
    for group, title in (("growth", "Growth"), ("profitability", "Profitability"),
                         ("balance_sheet", "Balance sheet"), ("cash_flow", "Cash flow"),
                         ("ownership", "Ownership")):
        st.markdown(f"**{title}**")
        values = data.get(group, {})
        st.dataframe(
            pd.DataFrame([{"metric": k, "value": v} for k, v in values.items()]),
            hide_index=True, use_container_width=True,
        )
    if data.get("red_flags"):
        st.error("Red flags: " + "; ".join(data["red_flags"]))


def render_technical(st) -> None:
    st.title("Technical Analysis")
    company_id = _pick_company(st, "tech")
    if company_id is None:
        return
    output = _show_agent(st, company_id, "technical_analysis", "technical")
    frame = components.price_frame(company_id)
    if not frame.empty:
        st.plotly_chart(components.candlestick_chart(frame.tail(250), "Daily candles"), use_container_width=True)
    if not output:
        return
    daily = output["data"].get("daily", {})
    st.markdown(f"**Assessment:** {output['data'].get('assessment', 'n/a')}")
    cols = st.columns(4)
    cols[0].metric("RSI(14)", f"{daily.get('rsi_14'):.1f}" if daily.get("rsi_14") is not None else "n/a")
    cols[1].metric("ADX(14)", f"{daily.get('adx_14'):.1f}" if daily.get("adx_14") is not None else "n/a")
    cols[2].metric("ATR(14)", f"{daily.get('atr_14'):.2f}" if daily.get("atr_14") is not None else "n/a")
    cols[3].metric("Rel. volume", f"{daily.get('relative_volume'):.2f}x" if daily.get("relative_volume") is not None else "n/a")
    st.write({
        "trend": daily.get("trend"), "trend_strength": daily.get("trend_strength"),
        "structure": (daily.get("price_structure") or {}).get("structure"),
        "support": daily.get("support"), "resistance": daily.get("resistance"),
        "breakout": daily.get("breakout"), "breakdown": daily.get("breakdown"),
        "divergence": daily.get("momentum_divergence"),
        "entry_zone": daily.get("entry_zone"),
        "invalidation_level": daily.get("invalidation_level"),
        "provisional_last_bar": daily.get("provisional_last_bar"),
        "emas": daily.get("emas"),
    })


def render_business(st) -> None:
    st.title("Business Quality")
    company_id = _pick_company(st, "biz")
    if company_id is None:
        return
    output = _show_agent(st, company_id, "business_quality", "business quality")
    if not output:
        return
    data = output["data"]
    st.markdown(f"**Classification:** {data.get('classification')}")
    st.caption(data.get("moat_assessment", ""))
    st.markdown("**Evidence**")
    for item in data.get("evidence", []):
        st.write("- " + item)
    st.markdown("**Not assessed (needs sources beyond free connectors)**")
    for item in data.get("unassessed_areas", []):
        st.write("- " + item)


def render_valuation(st) -> None:
    st.title("Valuation")
    company_id = _pick_company(st, "val")
    if company_id is None:
        return
    output = _show_agent(st, company_id, "valuation", "valuation")
    if not output:
        return
    data = output["data"]
    st.markdown("**Multiples**")
    st.dataframe(
        pd.DataFrame([{"metric": k, "value": v} for k, v in data.get("multiples", {}).items()]),
        hide_index=True, use_container_width=True,
    )
    if data.get("dcf"):
        st.markdown("**Valuation model (assumptions shown)**")
        st.json(data["dcf"])
        mos = data.get("margin_of_safety_vs_base_case")
        if mos is not None:
            st.metric("Margin of safety vs base case", f"{mos:.1%}")
    else:
        st.warning(f"Fair value not estimated: {data.get('dcf_not_calculated_reason')}")


def render_risk(st) -> None:
    st.title("Risk Analysis")
    company_id = _pick_company(st, "risk")
    if company_id is None:
        return
    output = _show_agent(st, company_id, "risk_analysis", "risk")
    if not output:
        return
    data = output["data"]
    classification = data.get("classification", "UNASSESSED")
    if classification in {"HIGH", "CRITICAL"}:
        st.error(f"Risk classification: {classification}")
    elif classification == "UNASSESSED":
        st.warning("Risk classification: UNASSESSED (no usable evidence)")
    else:
        st.success(f"Risk classification: {classification}")
    if data.get("coverage"):
        st.caption("Coverage: " + data["coverage"])
    findings = data.get("findings", [])
    if findings:
        st.dataframe(pd.DataFrame(findings), use_container_width=True, hide_index=True)
    st.markdown("**Unassessed governance items (not cleared, just unavailable)**")
    for item in data.get("unassessed_governance_items", []):
        st.write("- " + item)


def render_news(st) -> None:
    st.title("News Intelligence")
    from sqlalchemy import desc, select

    from database.connection import session_scope
    from database.models import NewsArticle

    with session_scope() as session:
        rows = session.scalars(
            select(NewsArticle).order_by(desc(NewsArticle.ingested_at)).limit(100)
        ).all()
    if not rows:
        st.info("No news yet. News is fetched during company research.")
        return
    st.caption("All headlines are UNVERIFIED signals, not confirmed financial evidence.")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "published": str(a.published_at), "headline": a.headline,
                    "sentiment": a.sentiment, "relevance": a.relevance,
                    "verification": a.verification_status, "source": a.source, "url": a.url,
                }
                for a in rows
            ]
        ),
        use_container_width=True, hide_index=True,
        column_config={"url": st.column_config.LinkColumn("link")},
    )
