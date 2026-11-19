"""Financial ratio calculations + missing-value behaviour."""
import pytest

from agents import fundamental_agent


def test_ratios_on_synthetic_statements(synthetic_statements, synthetic_info):
    result = fundamental_agent.analyze(synthetic_statements, synthetic_info, "Industrials")
    assert result.status == "success"
    prof = result.data["profitability"]
    # ROE = 17e7 / 80e7 = 0.2125
    assert prof["roe"] == pytest.approx(0.2125)
    # Net margin = 17/152
    assert prof["net_margin"] == pytest.approx(17 / 152)
    bs = result.data["balance_sheet"]
    assert bs["debt_to_equity"] == pytest.approx(8 / 80)
    assert bs["current_ratio"] == pytest.approx(40 / 25)
    cf = result.data["cash_flow"]
    assert cf["ocf_to_net_profit"] == pytest.approx(1.2)
    growth = result.data["growth"]
    assert growth["sales_growth_1y"] == pytest.approx(152 / 132 - 1)
    assert growth["sales_cagr_3y"] == pytest.approx((152 / 100) ** (1 / 3) - 1)


def test_missing_statements_fail_honestly(synthetic_info):
    empty = {"annual": {"income": {}, "balance": {}, "cashflow": {}}, "quarterly": {}}
    result = fundamental_agent.analyze(empty, synthetic_info, "Industrials")
    assert result.status == "failed"
    assert result.error
    assert result.data["profitability"]["roe"] is None
    assert "roe" in result.missing


def test_missing_values_never_invented(synthetic_statements, synthetic_info):
    broken = {"annual": {"income": {}, "balance": synthetic_statements["annual"]["balance"],
                         "cashflow": {}}, "quarterly": {}}
    result = fundamental_agent.analyze(broken, synthetic_info, "Industrials")
    assert result.data["growth"]["sales_cagr_3y"] is None
    assert result.data["cash_flow"]["operating_cash_flow"] is None
    assert "sales_cagr_3y" in result.missing or "operating_cash_flow" in result.missing


def test_financial_sector_skips_industrial_debt_rules(synthetic_statements, synthetic_info):
    result = fundamental_agent.analyze(synthetic_statements, synthetic_info, "Financial Services")
    assert result.data["is_financial_sector"] is True
    assert result.data["balance_sheet"]["debt_to_equity"] is None
    assert result.data["balance_sheet"]["current_ratio"] is None
    assert any("financial-sector" in w for w in result.warnings)


def test_cagr_sign_change_is_none():
    from data.validation import cagr

    assert cagr(-10, 20, 3) is None
    assert cagr(0, 20, 3) is None
    assert cagr(100, 121, 2) == pytest.approx(0.10)
