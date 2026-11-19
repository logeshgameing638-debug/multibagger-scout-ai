"""Offline tests for the hosted rotation updater logic (no network, no DB)."""
from __future__ import annotations

import json

import scripts.daily_update as du


def _universe(n: int) -> list[dict]:
    return [{"symbol": f"S{i:03d}", "name": f"Co {i}", "isin": ""} for i in range(n)]


def test_load_universe_reads_committed_csv(tmp_path):
    csv_path = tmp_path / "universe.csv"
    csv_path.write_text("symbol,name,isin\nAAA,Alpha,INE1\nBBB,Beta,\n")
    rows = du.load_universe(csv_path)
    assert [r["symbol"] for r in rows] == ["AAA", "BBB"]


def test_pick_batch_advances_cursor_and_wraps():
    universe = _universe(10)
    state = {"cursor": 0, "run_count": 0}
    batch, state = du.pick_batch(universe, state, 4)
    assert [r["symbol"] for r in batch] == ["S000", "S001", "S002", "S003"]
    assert state["cursor"] == 4
    batch, state = du.pick_batch(universe, state, 8)
    assert len(batch) == 6  # only 6 left before wrap
    assert state["cursor"] == 0
    batch, state = du.pick_batch(universe, state, 3)
    assert [r["symbol"] for r in batch] == ["S000", "S001", "S002"]


def test_pick_batch_stamps_cycle_start():
    batch, state = du.pick_batch(_universe(5), {"cursor": 0}, 2)
    assert state["cycle_started_at"]


def test_run_batch_records_every_stock_and_state(tmp_path, monkeypatch):
    monkeypatch.setattr(du, "UNIVERSE_CSV", tmp_path / "u.csv")
    monkeypatch.setattr(du, "SNAPSHOT_DIR", tmp_path / "snaps")
    monkeypatch.setattr(du, "STATE_FILE", tmp_path / "state.json")
    (tmp_path / "u.csv").write_text(
        "symbol,name,isin\nAAA,Alpha,\nBBB,Beta,\nCCC,Gamma,\n"
    )

    def fake_researcher(symbol: str) -> dict:
        if symbol == "BBB":
            raise RuntimeError("provider down")
        return {"symbol": symbol, "status": "complete", "updated_at": "2026-11-19 18:30 IST"}

    state = du.run_batch(
        batch_size=3, time_budget_minutes=5, sleep_seconds=0, researcher=fake_researcher
    )
    snaps = {p.stem: json.loads(p.read_text()) for p in (tmp_path / "snaps").glob("*.json")}
    assert set(snaps) == {"AAA", "BBB", "CCC"}
    assert snaps["BBB"]["status"] == "unavailable"
    assert "provider down" in snaps["BBB"]["error"]
    assert state["last_run"]["complete"] == 2
    assert state["last_run"]["unavailable"] == 1
    assert state["cursor"] == 0  # wrapped after consuming all 3


def test_run_batch_respects_time_budget(tmp_path, monkeypatch):
    monkeypatch.setattr(du, "UNIVERSE_CSV", tmp_path / "u.csv")
    monkeypatch.setattr(du, "SNAPSHOT_DIR", tmp_path / "snaps")
    monkeypatch.setattr(du, "STATE_FILE", tmp_path / "state.json")
    (tmp_path / "u.csv").write_text(
        "symbol,name,isin\n" + "\n".join(f"S{i},Co{i}," for i in range(10))
    )
    state = du.run_batch(
        batch_size=10,
        time_budget_minutes=0,  # budget already spent
        sleep_seconds=0,
        researcher=lambda s: {"symbol": s, "status": "complete"},
    )
    assert state["last_run"]["attempted"] == 0
    assert state["last_run"]["skipped_time_budget"] == 10
