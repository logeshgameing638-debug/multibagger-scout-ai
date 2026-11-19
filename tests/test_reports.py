"""CSV export + report generation (HTML/JSON/CSV/PDF) on synthetic bundles."""
import csv
import json
import os
from pathlib import Path

import pytest

from agents import fundamental_agent, technical_agent, valuation_agent, business_agent, risk_agent
from engine import report_generator
from engine.ranking import classify, combine_scores


@pytest.fixture()
def bundle(synthetic_statements, synthetic_info, synthetic_ohlcv, tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", os.environ["DATABASE_URL"])
    fundamentals = fundamental_agent.analyze(synthetic_statements, synthetic_info, "Industrials").data
    technicals = technical_agent.analyze(synthetic_ohlcv).data
    business = business_agent.analyze(fundamentals, synthetic_info).data
    valuation = valuation_agent.analyze(synthetic_info, fundamentals, 150.0).data
    risk = risk_agent.analyze(fundamentals, technicals, valuation, synthetic_info).data
    combined = combine_scores(70.0, 65.0)
    labels = classify(combined["balanced"], 70, 65, 10, "LOW", 70,
                      business["classification"], valuation.get("margin_of_safety_vs_base_case"))
    return {
        "symbol": "SYNTH", "exchange": "NSE", "name": "Synthetic Test Industries",
        "info": synthetic_info, "fundamentals": fundamentals, "technicals": technicals,
        "business": business, "valuation": valuation, "risk": risk,
        "news": {"items": [], "stored_new": 0},
        "scores": {"fundamental": 70.0, "technical": 65.0, "data_confidence": 60.0,
                   "risk": 10.0, **combined},
        "labels": labels,
        "explanation": {},
        "agent_statuses": {"fundamental": "success"},
        "generated_at": "2024-01-01T00:00:00",
    }


def test_report_has_all_17_sections(bundle):
    report = report_generator.build_report_dict(bundle)
    for number in range(1, 18):
        assert any(key.startswith(f"{number}_") for key in report), f"section {number} missing"
    assert "hypothesis" in report["disclaimer"] or "Not investment advice" in report["disclaimer"]


def test_generate_all_formats(bundle, monkeypatch, tmp_path):
    monkeypatch.setattr("config.settings._SETTINGS", None)
    import config.settings as settings_module

    settings = settings_module.get_settings()
    monkeypatch.setattr(settings_module.Settings, "exports_dir", property(lambda self: tmp_path))
    monkeypatch.setattr("engine.report_generator.get_settings", lambda: settings)

    paths = report_generator.generate_company_report(bundle, company_id=None)
    assert Path(paths["json"]).exists()
    assert Path(paths["html"]).exists()
    assert Path(paths["csv"]).exists()
    assert Path(paths["pdf"]).exists()  # reportlab installed

    data = json.loads(Path(paths["json"]).read_text())
    assert data["1_company_profile"]["symbol"] == "SYNTH"

    with open(paths["csv"]) as fh:
        rows = list(csv.reader(fh))
    assert rows[0] == ["section", "metric", "value"]
    assert any(row[0] == "scores" for row in rows[1:])

    html_text = Path(paths["html"]).read_text()
    assert "Multibagger Scout AI" in html_text
    assert "SYNTH" in html_text
