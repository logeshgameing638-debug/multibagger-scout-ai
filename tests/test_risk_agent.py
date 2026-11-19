"""Risk classification."""
from agents import risk_agent


def _base_fundamentals():
    return {
        "is_financial_sector": False,
        "balance_sheet": {"debt_to_equity": 0.3},
        "cash_flow": {"operating_cash_flow": 1e8, "ocf_to_net_profit": 1.1},
        "growth": {},
        "ownership": {"promoter_pledge_pct": None},
        "statements": {"annual": {"balance": {}}},
    }


def test_low_risk_classification():
    result = risk_agent.analyze(_base_fundamentals(), {"daily": {}}, {"multiples": {}})
    assert result.data["classification"] in {"LOW", "MODERATE"}
    assert result.data["unassessed_governance_items"]  # never silently cleared


def test_critical_debt_classification():
    fundamentals = _base_fundamentals()
    fundamentals["balance_sheet"]["debt_to_equity"] = 3.5
    result = risk_agent.analyze(fundamentals, {"daily": {}}, {"multiples": {}})
    assert result.data["classification"] == "CRITICAL"
    assert any(f["severity"] == "critical" for f in result.data["findings"])


def test_negative_ocf_high():
    fundamentals = _base_fundamentals()
    fundamentals["cash_flow"]["operating_cash_flow"] = -5e7
    result = risk_agent.analyze(fundamentals, {"daily": {}}, {"multiples": {}})
    assert result.data["classification"] == "HIGH"


def test_liquidity_flag():
    result = risk_agent.analyze(
        _base_fundamentals(), {"daily": {}}, {"multiples": {}},
        avg_daily_traded_value=5_000_000,
    )
    assert any(f["category"] == "liquidity" for f in result.data["findings"])


def test_findings_carry_evidence_and_date():
    fundamentals = _base_fundamentals()
    fundamentals["balance_sheet"]["debt_to_equity"] = 1.5
    result = risk_agent.analyze(fundamentals, {"daily": {}}, {"multiples": {}})
    finding = next(f for f in result.data["findings"] if f["category"] == "high_debt")
    assert finding["evidence"] and finding["date"] and finding["source"]
