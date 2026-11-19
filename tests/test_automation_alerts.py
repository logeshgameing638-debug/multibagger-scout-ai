"""Automation alert feed tests.

All prices/scores here are synthetic test data, never presented as live
market data. The feed itself must carry only market-derived research alerts -
no watchlists, holdings, orders or user activity.
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts import automation_alerts


def _write_snapshot(directory: Path, symbol: str, **overrides) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "symbol": symbol,
        "exchange": "NSE",
        "updated_at": "2026-11-18 18:35 IST",
        "status": "complete",
        "scores": {"balanced": 50.0, "risk": 20.0},
        "classification": "fairly_valued",
    }
    payload.update(overrides)
    (directory / f"{symbol}.json").write_text(json.dumps(payload))


def _run(tmp_path: Path, prev: dict | None = None) -> dict:
    snap_dir = tmp_path / "snapshots"
    feed_file = tmp_path / "automation" / "alerts_feed.json"
    prev_file = tmp_path / "automation" / "prev_scores.json"
    if prev is not None:
        prev_file.parent.mkdir(parents=True, exist_ok=True)
        prev_file.write_text(json.dumps(prev))
    return automation_alerts.run(snapshot_dir=snap_dir, feed_file=feed_file,
                                 prev_file=prev_file)


def _read_feed(tmp_path: Path) -> dict:
    return json.loads((tmp_path / "automation" / "alerts_feed.json").read_text())


def test_score_change_alert_fires_on_big_move(tmp_path):
    _write_snapshot(tmp_path / "snapshots", "AAA", scores={"balanced": 65.0, "risk": 20.0})
    _run(tmp_path, prev={"AAA": {"balanced": 50.0, "classification": "fairly_valued",
                                 "updated_at": "2026-11-11 18:35 IST"}})
    feed = _read_feed(tmp_path)
    moves = [a for a in feed["alerts"] if a["type"] == "score_change"]
    assert len(moves) == 1
    assert moves[0]["symbol"] == "AAA"
    assert "+15.0" in moves[0]["message"]
    assert moves[0]["severity"] == "warning"


def test_small_score_move_does_not_alert(tmp_path):
    _write_snapshot(tmp_path / "snapshots", "AAA", scores={"balanced": 55.0, "risk": 20.0})
    _run(tmp_path, prev={"AAA": {"balanced": 50.0, "classification": "fairly_valued",
                                 "updated_at": "2026-11-11 18:35 IST"}})
    feed = _read_feed(tmp_path)
    assert not [a for a in feed["alerts"] if a["type"] == "score_change"]


def test_high_stored_risk_alerts_critical(tmp_path):
    _write_snapshot(tmp_path / "snapshots", "RISKY", scores={"balanced": 40.0, "risk": 85.0})
    _run(tmp_path)
    feed = _read_feed(tmp_path)
    risk = [a for a in feed["alerts"] if a["type"] == "risk_high"]
    assert len(risk) == 1
    assert risk[0]["severity"] == "critical"


def test_technical_daily_rsi_and_breakout(tmp_path):
    _write_snapshot(
        tmp_path / "snapshots", "TECH",
        technical_daily={"rsi_14": 78.0, "breakout": True, "resistance": 512.0})
    _run(tmp_path)
    feed = _read_feed(tmp_path)
    types = {a["type"] for a in feed["alerts"]}
    assert "rsi_overbought" in types
    assert "breakout" in types


def test_rerun_does_not_duplicate_alerts_for_same_data(tmp_path):
    _write_snapshot(tmp_path / "snapshots", "AAA", scores={"balanced": 65.0, "risk": 80.0})
    _run(tmp_path)
    _run(tmp_path)  # second run over unchanged snapshots
    feed = _read_feed(tmp_path)
    keys = [(a["symbol"], a["type"], a["data_date"]) for a in feed["alerts"]]
    assert len(keys) == len(set(keys))
    assert feed["stats"]["new_alerts"] == 0


def test_feed_stats_and_prev_scores_written(tmp_path):
    _write_snapshot(tmp_path / "snapshots", "AAA", scores={"balanced": 60.0, "risk": 10.0})
    _write_snapshot(tmp_path / "snapshots", "BBB", scores={"balanced": 30.0, "risk": 10.0})
    _run(tmp_path)
    feed = _read_feed(tmp_path)
    assert feed["stats"]["snapshots_scanned"] == 2
    assert feed["generated_at"]
    prev = json.loads((tmp_path / "automation" / "prev_scores.json").read_text())
    assert prev["AAA"]["balanced"] == 60.0
    assert prev["BBB"]["classification"] == "fairly_valued"


def test_feed_contains_no_user_state(tmp_path):
    _write_snapshot(tmp_path / "snapshots", "AAA", scores={"balanced": 90.0, "risk": 80.0})
    _run(tmp_path)
    feed = _read_feed(tmp_path)
    blob = json.dumps(feed).lower()
    for forbidden in ("watchlist", "holding", "order", "position", "cash"):
        assert forbidden not in blob
