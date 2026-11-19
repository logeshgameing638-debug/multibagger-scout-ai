"""Tests for the scheduled automated research ranking feed (synthetic data)."""
import json
from pathlib import Path

from scripts import automation_rank


def _write_snapshot(directory: Path, symbol: str, balanced, status="complete",
                    risk=20.0, missing=None, updated="2026-11-18 18:35 IST") -> None:
    directory.mkdir(parents=True, exist_ok=True)
    agents = {"fundamental": "success", "technical": "success"}
    for m in (missing or []):
        agents[m] = "failed"
    payload = {
        "symbol": symbol,
        "exchange": "NSE",
        "updated_at": updated,
        "status": status,
        "agent_statuses": agents,
        "name": f"{symbol} Ltd",
        "scores": {"balanced": balanced, "risk": risk, "long_term": balanced,
                   "short_term": balanced, "data_confidence": 80.0},
        "classification": "fairly_valued",
    }
    (directory / f"{symbol}.json").write_text(json.dumps(payload))


def _run(tmp_path: Path) -> dict:
    return automation_rank.run(
        snapshot_dir=tmp_path / "snapshots",
        state_file=tmp_path / "rotation_state.json",
        feed_file=tmp_path / "automation" / "ranking_feed.json")


def test_ranking_sorted_by_balanced_desc(tmp_path):
    _write_snapshot(tmp_path / "snapshots", "LOW", 30.0)
    _write_snapshot(tmp_path / "snapshots", "HIGH", 80.0)
    _write_snapshot(tmp_path / "snapshots", "MID", 55.0)
    feed = _run(tmp_path)
    symbols = [r["symbol"] for r in feed["top"]]
    assert symbols == ["HIGH", "MID", "LOW"]
    assert [r["rank"] for r in feed["top"]] == [1, 2, 3]


def test_unavailable_and_unscored_excluded_and_counted(tmp_path):
    _write_snapshot(tmp_path / "snapshots", "OK", 60.0)
    _write_snapshot(tmp_path / "snapshots", "GONE", None, status="unavailable")
    _write_snapshot(tmp_path / "snapshots", "BROKEN", 10.0, status="system_error")
    feed = _run(tmp_path)
    assert feed["ranked_count"] == 1
    assert feed["excluded_count"] == 2
    assert feed["top"][0]["symbol"] == "OK"


def test_missing_agents_flagged(tmp_path):
    _write_snapshot(tmp_path / "snapshots", "PART", 50.0, status="partial",
                    missing=["technical"])
    feed = _run(tmp_path)
    assert feed["top"][0]["missing_agents"] == ["technical"]
    assert feed["top"][0]["data_date"] == "2026-11-18 18:35 IST"


def test_feed_written_with_run_context(tmp_path):
    _write_snapshot(tmp_path / "snapshots", "AAA", 70.0)
    (tmp_path / "rotation_state.json").write_text(json.dumps(
        {"last_run_at": "2026-11-19 10:00 IST", "universe_size": 2404,
         "cycle_started_at": "2026-11-19 09:36 IST"}))
    feed = _run(tmp_path)
    on_disk = json.loads((tmp_path / "automation" / "ranking_feed.json").read_text())
    assert on_disk["generated_at"]
    assert on_disk["rotation_last_run_at"] == "2026-11-19 10:00 IST"
    assert on_disk["universe_size"] == 2404


def test_feed_contains_no_user_state(tmp_path):
    _write_snapshot(tmp_path / "snapshots", "AAA", 90.0, risk=80.0)
    feed = _run(tmp_path)
    blob = json.dumps(feed).lower()
    for forbidden in ("watchlist", "holding", "order", "position", "cash"):
        assert forbidden not in blob
