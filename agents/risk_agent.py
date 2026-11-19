"""Agent 6 - Risk Analysis.

Every finding carries evidence, severity and a date. Governance items that
free sources cannot verify (auditor changes, related-party deals) are
reported as UNASSESSED, never silently cleared. A critical finding caps the
overall classification at CRITICAL regardless of scores elsewhere.
"""
from __future__ import annotations

from datetime import datetime, timezone

from .base import AgentResult

AGENT_NAME = "risk_analysis"

SEVERITY_ORDER = {"info": 0, "low": 1, "moderate": 2, "high": 3, "critical": 4}


def _finding(category: str, severity: str, evidence: str, source: str, date: str | None = None) -> dict:
    return {
        "category": category,
        "severity": severity,
        "evidence": evidence,
        "source": source,
        "date": date,
        "detected_at": str(datetime.now(timezone.utc)),
    }


def analyze(
    fundamentals: dict,
    technicals: dict,
    valuation: dict,
    info: dict | None = None,
    avg_daily_traded_value: float | None = None,
) -> AgentResult:
    result = AgentResult(agent_name=AGENT_NAME, status="success")
    info = info or {}
    findings: list[dict] = []
    today = str(datetime.now(timezone.utc).date())

    is_financial = fundamentals.get("is_financial_sector", False)
    bs = fundamentals.get("balance_sheet", {})
    cf = fundamentals.get("cash_flow", {})
    growth = fundamentals.get("growth", {})

    if not is_financial:
        d2e = bs.get("debt_to_equity")
        if d2e is not None and d2e > 2.0:
            findings.append(_finding("high_debt", "critical", f"debt/equity {d2e:.2f} (>2)", "yahoo_finance", today))
        elif d2e is not None and d2e > 1.0:
            findings.append(_finding("high_debt", "high", f"debt/equity {d2e:.2f} (>1)", "yahoo_finance", today))

    ocf = cf.get("operating_cash_flow")
    if ocf is not None and ocf < 0:
        findings.append(_finding("negative_ocf", "high", f"operating cash flow {ocf:,.0f} (negative)", "yahoo_finance", today))

    ocf_np = cf.get("ocf_to_net_profit")
    if ocf_np is not None and ocf_np < 0.5:
        findings.append(_finding("profit_quality", "moderate", f"OCF/net profit {ocf_np:.0%} (<50%)", "yahoo_finance", today))

    ownership = fundamentals.get("ownership", {})
    if ownership.get("promoter_pledge_pct") is None:
        result.missing.append("promoter pledge (not available from configured free sources)")

    shares_growth = None  # dilution needs share-count history; check via statements
    statements = fundamentals.get("statements", {}).get("annual", {})
    share_series = {
        p: m.get("Ordinary Shares Number")
        for p, m in statements.get("balance", {}).items()
        if m.get("Ordinary Shares Number")
    }
    if len(share_series) >= 2:
        dates = sorted(share_series)
        prev, last = share_series[dates[-2]], share_series[dates[-1]]
        if prev:
            shares_growth = (last - prev) / prev
            if shares_growth > 0.10:
                findings.append(_finding("equity_dilution", "moderate", f"share count +{shares_growth:.1%} YoY", "yahoo_finance", today))

    pe = valuation.get("multiples", {}).get("pe_trailing")
    if pe is not None and pe > 60:
        findings.append(_finding("high_valuation", "moderate", f"trailing P/E {pe:.0f} (>60)", "yahoo_finance", today))

    daily = technicals.get("daily", {})
    atr_pct = None
    if daily.get("atr_14") and daily.get("last_close"):
        atr_pct = daily["atr_14"] / daily["last_close"]
        if atr_pct > 0.04:
            findings.append(_finding("high_volatility", "moderate", f"ATR {atr_pct:.1%} of price (>4%)", "computed", today))

    beta = info.get("beta")
    if beta is not None and beta > 1.8:
        findings.append(_finding("high_volatility", "moderate", f"beta {beta:.2f} (>1.8)", "yahoo_finance", today))

    if avg_daily_traded_value is not None and avg_daily_traded_value < 10_000_000:
        findings.append(_finding("liquidity", "high", f"avg daily traded value Rs{avg_daily_traded_value:,.0f} (< Rs1 crore)", "yahoo_finance", today))

    unassessed = [
        "auditor resignation history",
        "qualified audit opinions",
        "related-party transactions",
        "regulatory actions",
        "promoter pledging (source unavailable)",
        "promoter selling (source unavailable)",
    ]

    quantitative_evidence = bool(bs or cf or growth)
    max_severity = max((SEVERITY_ORDER[f["severity"]] for f in findings), default=-1)
    if not quantitative_evidence and not findings:
        classification = "UNASSESSED"
    elif max_severity >= SEVERITY_ORDER["critical"]:
        classification = "CRITICAL"
    elif max_severity >= SEVERITY_ORDER["high"]:
        classification = "HIGH"
    elif max_severity >= SEVERITY_ORDER["moderate"]:
        classification = "MODERATE"
    else:
        classification = "LOW"

    # LOW never means "all clear": governance evidence is unavailable from
    # free sources, so coverage is always stated next to the class.
    coverage = (
        "quantitative checks only (debt, cash flow, profit quality, valuation, volatility, liquidity); "
        "governance items UNASSESSED - a LOW class does not clear them"
    )

    result.data = {
        "classification": classification,
        "findings": findings,
        "unassessed_governance_items": unassessed,
        "shares_outstanding_growth_yoy": shares_growth,
        "atr_pct_of_price": atr_pct,
        "coverage": coverage,
        "note": "governance items without a free verifiable source are UNASSESSED, not cleared",
    }
    result.missing.extend(unassessed)
    result.sources.append("yahoo_finance")
    return result.finish()
