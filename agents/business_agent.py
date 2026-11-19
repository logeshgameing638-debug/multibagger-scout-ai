"""Agent 4 - Business Quality.

Deterministic evidence-based classification. Free data sources cannot see
customer concentration, supplier dependency or management depth, so those are
explicitly marked unassessed rather than guessed. No moat is claimed without
evidence (multi-year margin stability + returns on capital are used as the
minimum evidence bar).
"""
from __future__ import annotations

from .base import AgentResult

AGENT_NAME = "business_quality"


def analyze(
    fundamentals: dict,
    info: dict | None = None,
) -> AgentResult:
    """fundamentals: data dict from the fundamental agent."""
    result = AgentResult(agent_name=AGENT_NAME, status="success")
    info = info or {}
    evidence: list[str] = []
    positive = 0
    negative = 0

    growth = fundamentals.get("growth", {})
    profitability = fundamentals.get("profitability", {})
    sector = info.get("sector")
    industry = info.get("industry")
    market_cap = info.get("marketCap")

    sales_5y = growth.get("sales_cagr_5y")
    if sales_5y is not None:
        if sales_5y > 0.12:
            positive += 1
            evidence.append(f"5y sales CAGR {sales_5y:.1%} (>12%): sustained demand growth")
        elif sales_5y < 0:
            negative += 1
            evidence.append(f"5y sales CAGR {sales_5y:.1%} (shrinking)")

    profit_5y = growth.get("profit_cagr_5y")
    if profit_5y is not None:
        if profit_5y > 0.12:
            positive += 1
            evidence.append(f"5y profit CAGR {profit_5y:.1%}: profitable growth")
        elif profit_5y < 0:
            negative += 1
            evidence.append(f"5y profit CAGR {profit_5y:.1%} (shrinking profits)")

    roe = profitability.get("roe")
    if roe is not None:
        if roe > 0.15:
            positive += 1
            evidence.append(f"ROE {roe:.1%} (>15%): capital allocated effectively")
        elif roe < 0.08:
            negative += 1
            evidence.append(f"ROE {roe:.1%} (<8%): weak returns on equity")

    op_margin = profitability.get("operating_margin")
    if op_margin is not None:
        if op_margin > 0.15:
            positive += 1
            evidence.append(f"operating margin {op_margin:.1%}: pricing power evidence")
        elif op_margin < 0.05:
            negative += 1
            evidence.append(f"operating margin {op_margin:.1%}: thin margins")

    for flag in fundamentals.get("red_flags", []):
        negative += 1
        evidence.append(f"red flag: {flag}")

    unassessed = [
        "business model detail (needs annual report reading)",
        "industry growth rate",
        "market share and competitor comparison",
        "customer concentration",
        "supplier dependency",
        "expansion projects / order book",
        "management quality and corporate governance depth",
    ]

    if positive + negative == 0:
        classification = "insufficient_evidence"
    elif positive >= 3 and negative == 0:
        classification = "strong"
    elif negative > positive:
        classification = "weak"
    else:
        classification = "average"

    if classification == "strong":
        moat_note = (
            "Quantitative evidence of durable economics exists (growth + returns + margins); "
            "a true moat still requires qualitative confirmation from annual reports."
        )
    else:
        moat_note = "No competitive moat claimed: insufficient qualitative evidence."

    result.data = {
        "classification": classification,
        "positive_evidence_count": positive,
        "negative_evidence_count": negative,
        "evidence": evidence,
        "sector": sector,
        "industry": industry,
        "market_cap": market_cap,
        "moat_assessment": moat_note,
        "unassessed_areas": unassessed,
    }
    result.missing = unassessed
    result.sources.append("yahoo_finance")
    return result.finish()
