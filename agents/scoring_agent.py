"""Agent 8 - Scoring. Transparent, reproducible scores with full explanations.

Point budgets (per spec):
  Fundamental 100: growth 20, ROE/ROCE 15, debt 15, cash flow 15,
                   promoter quality 15, valuation 10, industry growth 10
  Technical 100: long-term trend 20, EMA alignment 15, momentum 15,
                 volume 15, price structure 10, S/R 10, breakout 15
  Data confidence 100: source reliability 25, completeness 25, reporting
                       period 20, freshness 15, cross-source consistency 15
  Risk 100: higher = more risk. Derived from finding severities.

Missing values never earn full points: an unavailable input scores 0 for its
subscore and the explanation says exactly what was missing.
"""
from __future__ import annotations

from .base import AgentResult

AGENT_NAME = "scoring"


def _band(value: float | None, bands: list[tuple[float, float]], reverse: bool = False) -> tuple[float, str]:
    """bands: list of (threshold, points). First match wins.
    reverse=True rewards smaller values (e.g. debt)."""
    if value is None:
        return 0.0, "missing input: 0 points"
    ordered = sorted(bands, key=lambda b: b[0], reverse=not reverse)
    for threshold, points in ordered:
        if (value <= threshold) if reverse else (value >= threshold):
            return points, f"value {value:.3g} vs threshold {threshold:.3g}"
    return 0.0, f"value {value:.3g} below all bands"


def score_fundamental(fundamentals: dict, valuation: dict, business: dict) -> dict:
    explanation: dict[str, dict] = {}

    growth = fundamentals.get("growth", {})
    growth_parts = []
    growth_points = 0.0
    for key, weight in (("sales_cagr_3y", 5), ("sales_cagr_5y", 5), ("profit_cagr_3y", 5), ("profit_cagr_5y", 5)):
        pts, why = _band(growth.get(key), [(0.15, weight), (0.08, weight * 0.6), (0.0, weight * 0.3)])
        growth_points += pts
        growth_parts.append(f"{key}: {pts:.1f}/{weight} ({why})")
    explanation["growth"] = {"points": growth_points, "max": 20, "detail": growth_parts}

    prof = fundamentals.get("profitability", {})
    roe_pts, roe_why = _band(prof.get("roe"), [(0.20, 8), (0.15, 6), (0.10, 3)])
    roce_pts, roce_why = _band(prof.get("roce"), [(0.20, 7), (0.15, 5), (0.10, 3)])
    explanation["roe_roce"] = {
        "points": roe_pts + roce_pts, "max": 15,
        "detail": [f"roe: {roe_pts}/8 ({roe_why})", f"roce: {roce_pts}/7 ({roce_why})"],
    }

    bs = fundamentals.get("balance_sheet", {})
    if fundamentals.get("is_financial_sector"):
        explanation["debt_balance_sheet"] = {
            "points": 0.0, "max": 15,
            "detail": ["financial sector: industrial debt rules not applied; 0 awarded (not full points)"],
        }
    else:
        d2e_pts, d2e_why = _band(bs.get("debt_to_equity"), [(0.25, 8), (0.5, 6), (1.0, 3)], reverse=True)
        ic_pts, ic_why = _band(bs.get("interest_coverage"), [(8, 4), (4, 3), (2, 1)])
        cr_pts, cr_why = _band(bs.get("current_ratio"), [(1.5, 3), (1.0, 2)])
        explanation["debt_balance_sheet"] = {
            "points": d2e_pts + ic_pts + cr_pts, "max": 15,
            "detail": [f"debt/equity: {d2e_pts}/8 ({d2e_why})", f"interest cover: {ic_pts}/4 ({ic_why})", f"current ratio: {cr_pts}/3 ({cr_why})"],
        }

    cf = fundamentals.get("cash_flow", {})
    ocf_pts = 5.0 if (cf.get("operating_cash_flow") or 0) > 0 else 0.0
    fcf_pts = 5.0 if (cf.get("free_cash_flow") or 0) > 0 else 0.0
    conv_pts, conv_why = _band(cf.get("ocf_to_net_profit"), [(1.0, 5), (0.7, 3), (0.4, 1)])
    explanation["cash_flow"] = {
        "points": ocf_pts + fcf_pts + conv_pts, "max": 15,
        "detail": [
            f"positive OCF: {ocf_pts}/5" if cf.get("operating_cash_flow") is not None else "OCF missing: 0/5",
            f"positive FCF: {fcf_pts}/5" if cf.get("free_cash_flow") is not None else "FCF missing: 0/5",
            f"OCF/net profit: {conv_pts}/5 ({conv_why})",
        ],
    }

    ownership = fundamentals.get("ownership", {})
    insider = ownership.get("promoter_or_insider_holding_pct")
    if insider is None:
        promoter_pts, promoter_detail = 0.0, "promoter/insider holding missing: 0/10"
    else:
        promoter_pts, promoter_detail = _band(insider, [(0.5, 10), (0.3, 7), (0.1, 4)])
        promoter_detail = f"insider holding {insider:.1%}: {promoter_pts}/10"
    pledge_pts = 0.0  # pledge data unavailable from free sources -> no points
    explanation["management_promoter"] = {
        "points": promoter_pts + pledge_pts, "max": 15,
        "detail": [promoter_detail, "promoter pledge unavailable from free sources: 0/5"],
    }

    pe = valuation.get("multiples", {}).get("pe_trailing")
    ind_pe = valuation.get("multiples", {}).get("industry_pe")
    if pe is None:
        val_pts, val_why = 0.0, "P/E missing"
    elif ind_pe is not None and ind_pe > 0:
        ratio = pe / ind_pe
        val_pts, val_why = _band(ratio, [(0.8, 10), (1.0, 7), (1.3, 4)], reverse=True)
        val_why = f"P/E {pe:.1f} vs industry {ind_pe:.1f} (ratio {ratio:.2f}): {val_why}"
    else:
        val_pts, val_why = _band(pe, [(15, 8), (25, 6), (40, 3)], reverse=True)
        val_why = f"P/E {pe:.1f} (no industry benchmark): {val_why}"
    explanation["valuation"] = {"points": val_pts, "max": 10, "detail": [val_why]}

    industry_pts = 0.0
    industry_why = "industry growth unavailable from free sources: 0/10"
    explanation["industry_growth"] = {"points": industry_pts, "max": 10, "detail": [industry_why]}

    total = sum(part["points"] for part in explanation.values())
    return {"score": round(total, 1), "max": 100, "explanation": explanation}


def score_technical(technicals: dict) -> dict:
    explanation: dict[str, dict] = {}
    daily = technicals.get("daily", {})
    long_term = technicals.get("long_term_report", {})
    price = daily.get("last_close")

    trend = long_term.get("trend")
    lt_map = {"bullish": 20, "sideways": 10, "bearish": 3}
    lt_pts = lt_map.get(trend, 0)
    explanation["long_term_trend"] = {"points": lt_pts, "max": 20, "detail": [f"long-term trend: {trend}"]}

    emas = daily.get("emas", {})
    ema_pts = 0
    ema_detail = []
    if all(emas.get(k) is not None for k in ("ema_20", "ema_50", "ema_100", "ema_200")) and price:
        if price > emas["ema_20"] > emas["ema_50"] > emas["ema_100"] > emas["ema_200"]:
            ema_pts = 15
            ema_detail.append("full bullish alignment (price > 20 > 50 > 100 > 200)")
        elif price > emas["ema_50"]:
            ema_pts = 8
            ema_detail.append("price above EMA50, partial alignment")
        elif price > emas["ema_200"]:
            ema_pts = 5
            ema_detail.append("price above EMA200 only")
        else:
            ema_detail.append("below key EMAs")
    else:
        ema_detail.append("EMA values missing: 0/15")
    explanation["ema_alignment"] = {"points": ema_pts, "max": 15, "detail": ema_detail}

    rsi_v = daily.get("rsi_14")
    macd_hist = (daily.get("macd") or {}).get("histogram")
    rsi_pts, rsi_why = _band(rsi_v, [(55, 7), (45, 4)])
    macd_pts = 8.0 if (macd_hist or 0) > 0 else (0.0 if macd_hist is not None else 0.0)
    explanation["momentum"] = {
        "points": rsi_pts + macd_pts, "max": 15,
        "detail": [f"RSI {f'{rsi_v:.0f}' if rsi_v is not None else 'missing'}: {rsi_pts}/7 ({rsi_why})",
                   f"MACD histogram {'positive' if (macd_hist or 0) > 0 else 'non-positive/missing'}: {macd_pts}/8"],
    }

    rel_vol = daily.get("relative_volume")
    vol_pts, vol_why = _band(rel_vol, [(1.5, 15), (1.0, 10), (0.7, 5)])
    explanation["volume"] = {"points": vol_pts, "max": 15, "detail": [f"relative volume: {vol_why}"]}

    structure = (daily.get("price_structure") or {}).get("structure", "")
    if structure.startswith("uptrend"):
        ps_pts = 10
    elif structure.startswith("consolidation"):
        ps_pts = 5
    else:
        ps_pts = 2
    explanation["price_structure"] = {"points": ps_pts, "max": 10, "detail": [structure]}

    support, resistance = daily.get("support"), daily.get("resistance")
    sr_pts = 0
    sr_detail = []
    if support and resistance and price:
        span = resistance - support
        position = (price - support) / span if span > 0 else 0.5
        if 0.3 <= position <= 0.8:
            sr_pts = 10
            sr_detail.append(f"price mid-range between S/R ({position:.0%} of range)")
        elif position > 0.8:
            sr_pts = 6
            sr_detail.append("near resistance: reduced reward/risk")
        else:
            sr_pts = 4
            sr_detail.append("near support: watch for breakdown or bounce confirmation")
    else:
        sr_detail.append("support/resistance unavailable: 0/10")
    explanation["support_resistance"] = {"points": sr_pts, "max": 10, "detail": sr_detail}

    if daily.get("provisional_last_bar"):
        brk_pts = 0
        brk_detail = ["last bar provisional (intraday): breakout confirmation withheld"]
    elif daily.get("breakout"):
        brk_pts = 15
        brk_detail = ["confirmed breakout above resistance with volume >= 1.2x average"]
    else:
        brk_pts = 0
        brk_detail = ["no confirmed breakout"]
    explanation["breakout_confirmation"] = {"points": brk_pts, "max": 15, "detail": brk_detail}

    total = sum(part["points"] for part in explanation.values())
    return {"score": round(total, 1), "max": 100, "explanation": explanation}


def score_data_confidence(
    sources_ok: dict[str, bool],
    fundamentals_missing: list[str],
    technicals: dict,
    news_items: int,
    statements_periods: list[str],
    consistency_check: dict | None = None,
) -> dict:
    explanation: dict[str, dict] = {}

    reliability_weights = {"yahoo_finance": 10, "nse_archives": 10, "bse_site": 3, "rss_news": 2}
    rel_pts = sum(w for name, w in reliability_weights.items() if sources_ok.get(name))
    explanation["source_reliability"] = {
        "points": rel_pts, "max": 25,
        "detail": [f"{name}: {'ok' if ok else 'failed/unused'}" for name, ok in sources_ok.items()],
    }

    total_expected = 20
    completeness_pts = max(0.0, 25.0 * (1 - len(fundamentals_missing) / total_expected))
    explanation["completeness"] = {
        "points": round(completeness_pts, 1), "max": 25,
        "detail": [f"{len(fundamentals_missing)} fundamental metrics missing"],
    }

    years = len(statements_periods)
    period_pts, period_why = _band(float(years), [(4, 20), (3, 14), (2, 8), (1, 4)])
    explanation["reporting_period"] = {
        "points": period_pts, "max": 20,
        "detail": [f"{years} annual periods available ({period_why})"],
    }

    rows = technicals.get("rows_used", 0)
    fresh_pts, fresh_why = _band(float(rows), [(200, 15), (100, 10), (30, 5)])
    explanation["freshness_depth"] = {
        "points": fresh_pts, "max": 15,
        "detail": [f"{rows} validated daily bars ({fresh_why}); providers may delay quotes ~15 min"],
    }

    # Consistency is scored only from real comparisons of the same metric for
    # the same company and the same period across two independent sources.
    # Discovery/master-list success is NOT a financial-value comparison.
    checked = (consistency_check or {}).get("compared", 0)
    agreeing = (consistency_check or {}).get("agreeing", 0)
    if checked > 0:
        consistency_pts = round(15.0 * agreeing / checked, 1)
        detail = [f"{agreeing}/{checked} same-company, same-period values agree across sources"]
    else:
        consistency_pts = 0.0
        detail = ["not checked: no comparable same-company, same-period values from a second source"]
    explanation["cross_source_consistency"] = {
        "points": consistency_pts, "max": 15, "detail": detail,
    }

    total = sum(part["points"] for part in explanation.values())
    return {"score": round(total, 1), "max": 100, "explanation": explanation}


def score_risk(risk: dict) -> dict:
    """Higher score = greater risk. 100 = maximum measured risk."""
    weights = {"critical": 45, "high": 20, "moderate": 10, "low": 5, "info": 1}
    total = 0
    detail = []
    for finding in risk.get("findings", []):
        pts = weights.get(finding["severity"], 0)
        total += pts
        detail.append(f"{finding['category']} ({finding['severity']}): +{pts}")
    score = min(100, total)
    return {
        "score": score,
        "max": 100,
        "explanation": {
            "findings_contribution": {"points": score, "max": 100, "detail": detail or ["no findings"]},
            "classification": risk.get("classification", "UNASSESSED"),
            "unassessed_items": risk.get("unassessed_governance_items", []),
        },
    }


def analyze(
    fundamentals: dict,
    technicals: dict,
    business: dict,
    valuation: dict,
    risk: dict,
    sources_ok: dict[str, bool],
    news_items: int = 0,
) -> AgentResult:
    result = AgentResult(agent_name=AGENT_NAME, status="success")
    f_score = score_fundamental(fundamentals, valuation, business)
    t_score = score_technical(technicals)
    dc_score = score_data_confidence(
        sources_ok,
        fundamentals_missing=[],
        technicals=technicals,
        news_items=news_items,
        statements_periods=fundamentals.get("annual_periods", []),
    )
    r_score = score_risk(risk)
    result.data = {
        "fundamental": f_score,
        "technical": t_score,
        "data_confidence": dc_score,
        "risk": r_score,
    }
    return result.finish()
