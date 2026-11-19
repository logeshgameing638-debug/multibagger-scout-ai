"""BSE universe loading, interleaving and exchange-aware snapshot naming."""
import csv
import json
from pathlib import Path

import scripts.daily_update as du
import scripts.update_bse_universe as bu
from services import snapshots as snap_service


BHAVCOPY_SAMPLE = """TradDt,BizDt,SgmtId,SsnId,FinInstrmTp,FinInstrmId,ISIN,TckrSymb,SctySrs,OpnPric
2026-11-18,2026-11-18,1,1,STK,500002,INE000000001,ABB,EQ,6900.0
2026-11-18,2026-11-18,1,1,STK,500003,INE000000002,ACC,EQ,1800.0
2026-11-18,2026-11-18,1,1,STK,999999,INE000000009,DRILLBIT,X,10.0
"""


def test_parse_bhavcopy_equity_rows():
    rows = bu.parse_bhavcopy(BHAVCOPY_SAMPLE)
    symbols = [r["symbol"] for r in rows]
    assert symbols == ["ABB", "ACC"]  # X series excluded
    assert all(r["exchange"] == "BSE" for r in rows)
    assert rows[0]["session_date"] == "2026-11-18"
    assert rows[0]["isin"] == "INE000000001"


def test_write_and_load_bse_universe(tmp_path):
    out = tmp_path / "universe_bse.csv"
    bu.write_universe(bu.parse_bhavcopy(BHAVCOPY_SAMPLE), out)
    rows = du.load_bse_universe(out)
    assert [r["symbol"] for r in rows] == ["ABB", "ACC"]
    assert all(r["exchange"] == "BSE" for r in rows)


def test_interleave_spreads_bse_through_nse():
    nse = [{"symbol": f"N{i}", "exchange": "NSE"} for i in range(100)]
    bse = [{"symbol": f"B{i}", "exchange": "BSE"} for i in range(10)]
    combined = du.interleave(nse, bse)
    assert len(combined) == 110
    bse_positions = [i for i, r in enumerate(combined) if r["exchange"] == "BSE"]
    gaps = [b - a for a, b in zip(bse_positions, bse_positions[1:])]
    assert max(gaps) <= 12  # roughly every 10th slot
    # no symbol lost
    assert {r["symbol"] for r in combined} == {r["symbol"] for r in nse + bse}


def test_interleave_edge_cases():
    nse = [{"symbol": "A", "exchange": "NSE"}]
    assert du.interleave(nse, []) == nse
    bse = [{"symbol": "B", "exchange": "BSE"}]
    assert du.interleave([], bse) == bse


def test_bse_snapshot_naming_avoids_nse_collision(tmp_path, monkeypatch):
    monkeypatch.setattr(du, "SNAPSHOT_DIR", tmp_path)
    du.write_snapshot("ABB", {"symbol": "ABB", "exchange": "NSE"})
    du.write_snapshot("ABB", {"symbol": "ABB", "exchange": "BSE"})
    assert (tmp_path / "ABB.json").exists()
    assert (tmp_path / "BSE_ABB.json").exists()
    loaded = snap_service.load_snapshots(tmp_path)
    assert set(loaded) == {"ABB", "BSE_ABB"}
    monkeypatch.setattr(snap_service, "SNAPSHOT_DIR", tmp_path)
    assert snap_service.get_snapshot("ABB", "BSE")["exchange"] == "BSE"
    assert snap_service.get_snapshot("ABB", "NSE")["exchange"] == "NSE"


def test_run_batch_threads_exchange(tmp_path, monkeypatch):
    monkeypatch.setattr(du, "SNAPSHOT_DIR", tmp_path / "snaps")
    monkeypatch.setattr(du, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(du, "UNIVERSE_GLOB", "none*.csv")
    monkeypatch.setattr(du, "UNIVERSE_CSV", tmp_path / "none.csv")
    nse_csv = tmp_path / "nse.csv"
    with open(nse_csv, "w", newline="") as h:
        csv.DictWriter(h, fieldnames=["symbol", "name"]).writeheader()
    monkeypatch.setattr(du, "BSE_UNIVERSE_CSV", tmp_path / "bse.csv")
    bu.write_universe(bu.parse_bhavcopy(BHAVCOPY_SAMPLE), tmp_path / "bse.csv")
    import database
    monkeypatch.setattr(database, "init_db", lambda: None)
    monkeypatch.setattr(du, "init_db", lambda: None, raising=False)

    calls = []

    def fake(symbol, exchange="NSE"):
        calls.append((symbol, exchange))
        return {"symbol": symbol, "exchange": exchange, "status": "complete",
                "updated_at": "2026-11-19 19:00 IST"}

    state = du.run_batch(batch_size=2, time_budget_minutes=5, sleep_seconds=0,
                         researcher=fake)
    assert calls and all(ex == "BSE" for _, ex in calls)
    assert state["universe_breakdown"] == {"NSE": 0, "BSE": 2}
    assert (tmp_path / "snaps" / "BSE_ABB.json").exists()
