"""Tests for automated narrative report generation (synthetic, mocked research)."""
import json
from pathlib import Path

from scripts import automation_reports


def _ranking(tmp_path: Path, symbols) -> Path:
    feed = tmp_path / "automation" / "ranking_feed.json"
    feed.parent.mkdir(parents=True, exist_ok=True)
    feed.write_text(json.dumps({
        "generated_at": "2026-11-19 14:17 IST",
        "top": [{"symbol": s, "exchange": "NSE", "balanced": 60.0,
                 "data_date": "2026-11-19 14:11 IST"} for s in symbols],
    }))
    return feed


def test_no_candidates_returns_skipped(tmp_path):
    feed = _ranking(tmp_path, [])
    result = automation_reports.generate_top_reports(
        ranking_feed=feed, reports_dir=tmp_path / "reports")
    assert result["skipped"] == "no ranked candidates"
    assert result["reports"] == []


def test_reports_generated_and_manifest_written(tmp_path, monkeypatch):
    feed = _ranking(tmp_path, ["AAA", "BBB"])
    exports = tmp_path / "exports"
    exports.mkdir()

    def fake_research(symbol, exchange, generate_report=True):
        assert generate_report is True
        path = exports / f"{symbol}_{exchange}_research.json"
        path.write_text(json.dumps({"symbol": symbol, "summary": "synthetic test report"}))
        return {"status": "success", "reports": {"json": str(path)},
                "agent_statuses": {"fundamental": "success"}}

    monkeypatch.setattr("engine.orchestrator.research_company", fake_research)
    monkeypatch.setattr("database.init_db", lambda: None)

    result = automation_reports.generate_top_reports(
        ranking_feed=feed, reports_dir=tmp_path / "reports")
    assert len(result["reports"]) == 2
    report_file = tmp_path / "reports" / "NSE_AAA.json"
    assert report_file.exists()
    payload = json.loads(report_file.read_text())
    assert payload["summary"] == "synthetic test report"
    assert payload["automation"]["source"] == "scheduled GitHub Actions run"
    assert payload["automation"]["rotation_data_date"] == "2026-11-19 14:11 IST"
    manifest = json.loads((tmp_path / "reports" / "manifest.json").read_text())
    assert manifest["reports"][0]["symbol"] == "AAA"
    assert manifest["generated_at"]


def test_one_candidate_failure_does_not_kill_batch(tmp_path, monkeypatch):
    feed = _ranking(tmp_path, ["BAD", "GOOD"])

    def fake_research(symbol, exchange, generate_report=True):
        if symbol == "BAD":
            raise RuntimeError("synthetic failure")
        path = tmp_path / "exports" / f"{symbol}_x.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text("{}")
        return {"status": "partial", "reports": {"json": str(path)}, "agent_statuses": {}}

    monkeypatch.setattr("engine.orchestrator.research_company", fake_research)
    monkeypatch.setattr("database.init_db", lambda: None)

    result = automation_reports.generate_top_reports(
        ranking_feed=feed, reports_dir=tmp_path / "reports")
    statuses = {r["symbol"]: r["status"] for r in result["reports"]}
    assert statuses == {"BAD": "system_error", "GOOD": "partial"}
    assert "synthetic failure" in result["reports"][0]["error"]


def test_html_csv_exports_committed_alongside_json(tmp_path, monkeypatch):
    feed = _ranking(tmp_path, ["AAA"])
    exports = tmp_path / "exports"
    exports.mkdir()

    def fake_research(symbol, exchange, generate_report=True):
        paths = {}
        for fmt, body in (("json", '{"symbol": "%s"}' % symbol),
                          ("html", "<html>report</html>"),
                          ("csv", "section,metric,value\n")):
            path = exports / f"{symbol}_{exchange}_research.{fmt}"
            path.write_text(body)
            paths[fmt] = str(path)
        return {"status": "success", "reports": paths, "agent_statuses": {}}

    monkeypatch.setattr("engine.orchestrator.research_company", fake_research)
    monkeypatch.setattr("database.init_db", lambda: None)

    result = automation_reports.generate_top_reports(
        ranking_feed=feed, reports_dir=tmp_path / "reports")
    entry = result["reports"][0]
    assert (tmp_path / "reports" / "NSE_AAA.html").exists()
    assert (tmp_path / "reports" / "NSE_AAA.csv").exists()
    assert entry["exports"]["html"].endswith("NSE_AAA.html")
    assert entry["exports"]["csv"].endswith("NSE_AAA.csv")
