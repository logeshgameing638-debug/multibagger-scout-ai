"""Shape an automated research report JSON into readable narrative sections
for the hosted UI. Pure data shaping, no Streamlit, so it is unit-testable.
Every section preserves the report's own timestamps, missing-data lists and
source attributions - nothing is invented here."""

from __future__ import annotations


def _pct(v) -> str:
    if v is None:
        return "n/a"
    try:
        return f"{float(v) * 100:.1f}%"
    except (TypeError, ValueError):
        return str(v)


def _num(v) -> str:
    if v is None:
        return "n/a"
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if abs(f) >= 1e7:
        return f"{f / 1e7:,.1f} Cr"
    return f"{f:,.2f}"


def _score(v) -> str:
    if v is None:
        return "n/a"
    try:
        return f"{float(v):.0f}/100"
    except (TypeError, ValueError):
        return str(v)


def _kv_rows(d: dict, formatter) -> list[tuple[str, str]]:
    rows = []
    for k, v in (d or {}).items():
        rows.append((k.replace("_", " "), formatter(v)))
    return rows


def build_narrative(report: dict) -> dict:
    """Return ordered narrative sections for one automated report."""
    profile = report.get("1_company_profile", {}) or {}
    stamp = report.get("2_source_and_timestamp", {}) or {}
    fin = report.get("3_financial_analysis", {}) or {}
    tech = report.get("4_technical_analysis", {}) or {}
    quality = report.get("5_business_quality", {}) or {}
    val = report.get("6_valuation", {}) or {}
    news = report.get("7_news_intelligence", {}) or {}
    risk = report.get("8_risk_analysis", {}) or {}
    short = report.get("12_short_term_assessment", {}) or {}
    long_ = report.get("13_long_term_assessment", {}) or {}
    missing = report.get("16_missing_evidence", {}) or {}

    header = {
        "title": f"{profile.get('name') or report.get('symbol', '')} ({profile.get('symbol', '')}, {profile.get('exchange', '')})",
        "subtitle": ", ".join(x for x in [profile.get("sector"), profile.get("industry")] if x),
        "market_cap": _num(profile.get("market_cap")),
        "generated_at": stamp.get("generated_at"),
        "data_date": (report.get("automation") or {}).get("rotation_data_date"),
        "price_note": stamp.get("price_note"),
    }

    scores = {
        "Fundamental": _score(report.get("9_fundamental_score")),
        "Technical": _score(report.get("10_technical_score")),
        "Data confidence": _score(report.get("11_data_confidence")),
        "Long term": _score((report.get("combined_scores") or {}).get("long_term")),
        "Short term": _score((report.get("combined_scores") or {}).get("short_term")),
        "Balanced": _score((report.get("combined_scores") or {}).get("balanced")),
        "Risk (higher is worse)": _score((report.get("combined_scores") or {}).get("risk_score_higher_is_worse")),
        "Labels": ", ".join(report.get("labels") or []) or "none",
    }

    tv = short.get("technical_view") or {}
    short_view = {
        "score": _score(short.get("score")),
        "trend": tv.get("trend"),
        "rsi_14": _num(tv.get("rsi_14")),
        "entry_zone": short.get("entry_zone"),
        "invalidation_level": short.get("invalidation_level"),
    }
    lt = long_.get("trend") or {}
    long_view = {
        "score": _score(long_.get("score")),
        "trend": lt.get("trend"),
        "price_vs_ema_200": lt.get("price_vs_ema_200"),
        "business_classification": long_.get("business_classification"),
    }

    financials = {
        "Growth": _kv_rows(fin.get("growth"), _pct),
        "Profitability": _kv_rows(fin.get("profitability"), _pct),
        "Balance sheet": _kv_rows(fin.get("balance_sheet"), _num),
        "Cash flow": _kv_rows(fin.get("cash_flow"), _num),
        "Ownership": _kv_rows(fin.get("ownership"), _pct),
        "red_flags": fin.get("red_flags") or [],
        "periods": f"{len(fin.get('annual_periods') or [])} annual, {len(fin.get('quarterly_periods') or [])} quarterly periods on record",
    }

    multiples = val.get("multiples") or {}
    valuation = {
        "multiples": _kv_rows(multiples, _num),
        "view": val.get("valuation_view_vs_industry"),
        "dcf": val.get("dcf"),
        "dcf_not_calculated_reason": val.get("dcf_not_calculated_reason"),
        "margin_of_safety": val.get("margin_of_safety_vs_base_case"),
        "current_price": _num(val.get("current_price")),
    }

    business = {
        "classification": quality.get("classification"),
        "moat": quality.get("moat_assessment"),
        "positive_evidence": quality.get("positive_evidence_count"),
        "negative_evidence": quality.get("negative_evidence_count"),
        "unassessed": quality.get("unassessed_areas") or [],
    }

    news_items = news.get("items") or []
    news_sec = {
        "count": len(news_items),
        "note": news.get("note"),
        "headlines": [(i.get("title") or i.get("headline") or str(i)[:120],
                       i.get("published") or i.get("date")) for i in news_items[:5] if isinstance(i, (dict, str))],
    }

    risk_sec = {
        "classification": risk.get("classification"),
        "findings": risk.get("findings") or [],
        "unassessed_governance": risk.get("unassessed_governance_items") or [],
        "coverage": risk.get("coverage"),
        "note": risk.get("note"),
    }

    missing_sec = []
    for key in ("fundamental_gaps", "unassessed_governance", "valuation_gaps", "business_unassessed"):
        items = missing.get(key)
        if items:
            label = key.replace("_", " ")
            missing_sec.append((label, items if isinstance(items, list) else [str(items)]))

    return {
        "header": header,
        "scores": scores,
        "thesis": report.get("14_investment_thesis"),
        "invalidation": report.get("15_thesis_invalidation") or [],
        "short_term": short_view,
        "long_term": long_view,
        "technical_assessment": tech.get("assessment"),
        "financials": financials,
        "valuation": valuation,
        "business_quality": business,
        "news": news_sec,
        "risks": risk_sec,
        "missing": missing_sec,
        "sources": report.get("17_sources") or [],
        "disclaimer": report.get("disclaimer"),
    }
