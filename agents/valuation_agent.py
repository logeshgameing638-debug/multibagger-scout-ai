"""Agent 5 - Valuation.

Multiples from provider data; DCF only when enough free cash flow history
exists, with every assumption shown. Financial-sector companies use a P/B-ROE
justified-valuation method. When data is insufficient, fair value is None
with the reason stated - never a fake target.
"""
from __future__ import annotations

from .base import AgentResult

AGENT_NAME = "valuation"

DEFAULT_COST_OF_EQUITY = 0.13  # India large-cap equity hurdle, documented assumption
DEFAULT_TERMINAL_GROWTH = 0.05
DEFAULT_PROJECTION_YEARS = 10


def _dcf(
    base_fcf: float,
    growth_rates: tuple[float, float, float],
    shares_outstanding: float | None,
    cost_of_equity: float = DEFAULT_COST_OF_EQUITY,
    terminal_growth: float = DEFAULT_TERMINAL_GROWTH,
    years: int = DEFAULT_PROJECTION_YEARS,
) -> dict:
    """Three-scenario DCF. All assumptions returned alongside values."""
    scenarios: dict[str, float | None] = {}
    for label, g in zip(("bear", "base", "bull"), growth_rates):
        fcf = base_fcf
        present_value = 0.0
        for year in range(1, years + 1):
            fcf *= 1 + g
            present_value += fcf / (1 + cost_of_equity) ** year
        terminal_value = fcf * (1 + terminal_growth) / (cost_of_equity - terminal_growth)
        present_value += terminal_value / (1 + cost_of_equity) ** years
        scenarios[label] = present_value / shares_outstanding if shares_outstanding else None
    return {
        "scenarios": scenarios,
        "assumptions": {
            "base_fcf": base_fcf,
            "growth_rates": {"bear": growth_rates[0], "base": growth_rates[1], "bull": growth_rates[2]},
            "cost_of_equity": cost_of_equity,
            "terminal_growth": terminal_growth,
            "projection_years": years,
            "shares_outstanding": shares_outstanding,
        },
    }


def analyze(
    info: dict,
    fundamentals: dict,
    current_price: float | None,
    industry_pe: float | None = None,
) -> AgentResult:
    result = AgentResult(agent_name=AGENT_NAME, status="success")
    is_financial = fundamentals.get("is_financial_sector", False)

    multiples = {
        "pe_trailing": info.get("trailingPE"),
        "pe_forward": info.get("forwardPE"),
        "pb": info.get("priceToBook"),
        "ev_ebitda": info.get("enterpriseToEbitda"),
        "ev_sales": info.get("enterpriseToRevenue"),
        "peg": info.get("pegRatio"),
        "dividend_yield": info.get("dividendYield"),
        "industry_pe": industry_pe,
    }
    missing_multiples = [k for k, v in multiples.items() if v is None]

    dcf_result = None
    dcf_reason = None
    margin_of_safety = None
    if is_financial:
        dcf_reason = "financial-sector company: P/B vs ROE method used instead of FCF DCF"
        roe = fundamentals.get("profitability", {}).get("roe")
        pb = info.get("priceToBook")
        growth = fundamentals.get("growth", {}).get("profit_cagr_5y") or 0.04
        g = min(max(growth, 0.0), 0.10)
        if roe and roe > DEFAULT_TERMINAL_GROWTH:
            justified_pb = (roe - g) / (DEFAULT_COST_OF_EQUITY - g)
            dcf_result = {
                "method": "justified P/B (financial sector)",
                "justified_pb": justified_pb,
                "actual_pb": pb,
                "view": (
                    "undervalued vs justified P/B" if pb and pb < justified_pb * 0.85
                    else "overvalued vs justified P/B" if pb and pb > justified_pb * 1.15
                    else "fairly valued vs justified P/B" if pb else "P/B unavailable"
                ),
                "assumptions": {"roe": roe, "growth": g, "cost_of_equity": DEFAULT_COST_OF_EQUITY},
            }
        else:
            dcf_reason = "ROE unavailable or too low for justified-P/B method"
    else:
        cash_flow = fundamentals.get("cash_flow", {})
        fcf = cash_flow.get("free_cash_flow")
        shares = info.get("sharesOutstanding")
        profit_cagr = fundamentals.get("growth", {}).get("profit_cagr_5y")
        if fcf and fcf > 0 and shares:
            base_growth = min(max(profit_cagr if profit_cagr is not None else 0.08, 0.0), 0.20)
            growth_rates = (base_growth * 0.5, base_growth, base_growth * 1.25)
            dcf_result = _dcf(fcf, growth_rates, shares)
            base_fair = dcf_result["scenarios"]["base"]
            if base_fair and current_price:
                margin_of_safety = (base_fair - current_price) / base_fair
        else:
            dcf_reason = (
                "positive free cash flow history and share count required; "
                f"fcf={'available' if fcf else 'missing'}, shares={'available' if shares else 'missing'}"
            )

    pe = multiples["pe_trailing"]
    valuation_view = None
    if pe is not None and industry_pe is not None:
        if pe < industry_pe * 0.8:
            valuation_view = "below industry P/E"
        elif pe > industry_pe * 1.2:
            valuation_view = "above industry P/E"
        else:
            valuation_view = "in line with industry P/E"

    result.data = {
        "multiples": multiples,
        "valuation_view_vs_industry": valuation_view,
        "dcf": dcf_result,
        "dcf_not_calculated_reason": None if dcf_result else dcf_reason,
        "margin_of_safety_vs_base_case": margin_of_safety,
        "current_price": current_price,
    }
    result.missing = missing_multiples
    result.sources.append("yahoo_finance")
    if not dcf_result:
        result.status = "partial"
    return result.finish()
