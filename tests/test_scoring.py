"""Fundamental/technical scoring, data confidence, ranking."""
import pytest

from agents import fundamental_agent, scoring_agent, technical_agent, valuation_agent
from engine.ranking import classify, combine_scores, rank_candidates


@pytest.fixture()
def agent_outputs(synthetic_statements, synthetic_info, synthetic_ohlcv):
    fundamentals = fundamental_agent.analyze(synthetic_statements, synthetic_info, "Industrials").data
    technicals = technical_agent.analyze(synthetic_ohlcv).data
    business = {"classification": "strong", "evidence": []}
    valuation = valuation_agent.analyze(synthetic_info, fundamentals, 150.0).data
    risk = {"classification": "LOW", "findings": [], "unassessed_governance_items": []}
    return fundamentals, technicals, business, valuation, risk


def test_fundamental_score_structure(agent_outputs):
    fundamentals, _, business, valuation, _ = agent_outputs
    scored = scoring_agent.score_fundamental(fundamentals, valuation, business)
    assert 0 <= scored["score"] <= 100
    budgets = {k: v["max"] for k, v in scored["explanation"].items()}
    assert budgets == {
        "growth": 20, "roe_roce": 15, "debt_balance_sheet": 15, "cash_flow": 15,
        "management_promoter": 15, "valuation": 10, "industry_growth": 10,
    }
    # industry growth unavailable from free sources -> 0, not full points
    assert scored["explanation"]["industry_growth"]["points"] == 0


def test_missing_inputs_score_zero_not_full(synthetic_info, synthetic_ohlcv):
    empty_fundamentals = {
        "growth": {}, "profitability": {}, "balance_sheet": {}, "cash_flow": {},
        "ownership": {}, "is_financial_sector": False,
    }
    valuation = {"multiples": {}}
    scored = scoring_agent.score_fundamental(empty_fundamentals, valuation, {})
    assert scored["score"] == 0


def test_technical_score_structure(agent_outputs):
    _, technicals, _, _, _ = agent_outputs
    scored = scoring_agent.score_technical(technicals)
    assert 0 <= scored["score"] <= 100
    budgets = {k: v["max"] for k, v in scored["explanation"].items()}
    assert budgets == {
        "long_term_trend": 20, "ema_alignment": 15, "momentum": 15, "volume": 15,
        "price_structure": 10, "support_resistance": 10, "breakout_confirmation": 15,
    }


def test_data_confidence_partial_sources():
    scored = scoring_agent.score_data_confidence(
        {"yahoo_finance": True, "nse_archives": False, "bse_site": False, "rss_news": False},
        fundamentals_missing=["roe", "fcf"],
        technicals={"rows_used": 250},
        news_items=5,
        statements_periods=["2021", "2022", "2023", "2024"],
    )
    assert 0 < scored["score"] < 100
    assert scored["explanation"]["source_reliability"]["points"] == 10  # yahoo only


def test_combine_scores_weights():
    combined = combine_scores(80.0, 60.0)
    assert combined["long_term"] == pytest.approx(0.7 * 80 + 0.3 * 60)
    assert combined["short_term"] == pytest.approx(0.7 * 60 + 0.3 * 80)
    assert combined["balanced"] == pytest.approx(70.0)


def test_rank_candidates_none_last():
    rows = [
        {"symbol": "A", "balanced": 50.0},
        {"symbol": "B", "balanced": None},
        {"symbol": "C", "balanced": 70.0},
    ]
    ranked = rank_candidates(rows)
    assert [r["symbol"] for r in ranked] == ["C", "A", "B"]


def test_classify_multibagger_is_hypothesis():
    labels = classify(
        balanced=75, fundamental=70, technical=70, risk_score=10,
        risk_classification="LOW", data_confidence=70,
        business_classification="strong", margin_of_safety=0.3,
    )
    assert "potential_multibagger_hypothesis" in labels
    assert "high_risk" not in labels


def test_classify_high_risk_blocks_multibagger():
    labels = classify(
        balanced=75, fundamental=70, technical=70, risk_score=60,
        risk_classification="HIGH", data_confidence=70,
        business_classification="strong", margin_of_safety=0.3,
    )
    assert "high_risk" in labels
    assert "potential_multibagger_hypothesis" not in labels
