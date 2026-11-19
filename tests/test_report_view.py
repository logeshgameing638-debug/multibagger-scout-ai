import json
from pathlib import Path

from services.report_view import build_narrative

FIXTURE = Path(__file__).resolve().parent.parent / "data" / "automation" / "reports" / "NSE_BANCOINDIA.json"


def test_narrative_from_real_report():
    report = json.loads(FIXTURE.read_text())
    n = build_narrative(report)
    assert "BANCOINDIA" in n["header"]["title"]
    assert n["header"]["generated_at"]
    assert n["scores"]["Fundamental"].endswith("/100")
    assert isinstance(n["thesis"], str) and len(n["thesis"]) > 40
    assert isinstance(n["invalidation"], list) and n["invalidation"]
    assert n["financials"]["Growth"], "growth rows expected"
    assert any("%" in v for _, v in n["financials"]["Profitability"])
    assert n["sources"], "dated sources must be listed"
    assert n["missing"], "missing-evidence section must survive"
    assert n["disclaimer"]


def test_narrative_tolerates_missing_sections():
    n = build_narrative({"1_company_profile": {"symbol": "X", "exchange": "NSE"}})
    assert n["header"]["title"].startswith("(X, NSE)") or "X" in n["header"]["title"]
    assert n["scores"]["Fundamental"] == "n/a"
    assert n["thesis"] is None
    assert n["financials"]["Growth"] == []
    assert n["missing"] == []
    assert n["sources"] == []
