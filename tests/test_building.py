"""Paper trading, portfolio and command-center services."""
import pandas as pd
import pytest

from database.connection import init_db
from services import building, paper_trading


@pytest.fixture()
def fresh_db(tmp_path):
    init_db(f"sqlite:///{tmp_path}/building_test.db")
    yield


class _Result:
    def __init__(self, ok, data=None, error=None):
        self.ok = ok
        self.data = data or {}
        self.error = error


class _StubYF:
    name = "yahoo_finance"

    def get_history(self, symbol, exchange, period="5d", interval="1d"):
        frame = pd.DataFrame(
            {"open": [100.0], "high": [105.0], "low": [99.0],
             "close": [100.0], "volume": [1000]},
            index=pd.date_range("2026-11-18", periods=1))
        return _Result(True, {"frame": frame})


class _StubRegistry:
    def get(self, name):
        return _StubYF()


@pytest.fixture()
def stub_yf(monkeypatch):
    monkeypatch.setattr("data.connectors.default_registry", lambda: _StubRegistry())
    monkeypatch.setattr(paper_trading, "_latest_price", lambda s, e: (100.0, "2026-11-18"))


def test_paper_buy_sell_and_pnl(fresh_db, stub_yf):
    out = paper_trading.place_order("AAA", "NSE", "BUY", 10, stop_loss=90.0, target=130.0)
    assert out["ok"] and out["simulated"] and out["fill_price"] == 100.0
    assert paper_trading.virtual_cash() == 1_000_000.0 - 1000.0
    summary = paper_trading.portfolio_summary()
    assert summary["simulated"] and len(summary["holdings"]) == 1
    holding = summary["holdings"][0]
    assert holding["qty"] == 10 and holding["avg_cost"] == 100.0
    out2 = paper_trading.place_order("AAA", "NSE", "SELL", 4)
    assert out2["ok"]
    summary = paper_trading.portfolio_summary()
    assert summary["holdings"][0]["qty"] == 6
    assert len(paper_trading.trade_history()) == 2


def test_paper_order_guards(fresh_db, stub_yf):
    assert not paper_trading.place_order("AAA", "NSE", "BUY", 0)["ok"]
    assert not paper_trading.place_order("AAA", "NSE", "HOLD", 5)["ok"]
    big = paper_trading.place_order("AAA", "NSE", "BUY", 10_000_000)
    assert not big["ok"] and "insufficient virtual cash" in big["error"]
    assert not paper_trading.place_order("NOPE", "NSE", "SELL", 5)["ok"]


def test_command_status_and_logs(fresh_db):
    status = building.command_status()
    assert status["database_ok"] is True
    assert status["companies"] == 0
    floors = building.floor_activity()
    assert set(floors) == {0, 1, 2, 3, 4, 5, 6, 7}
    assert all(f["running"] is False for f in floors.values())
    assert building.activity_log() == []


def test_reset_paper_account_restores_clean_state(monkeypatch):
    monkeypatch.setattr(paper_trading, "_latest_price", lambda symbol, exchange: (100.0, "2026-11-19"))
    paper_trading.place_order("ZZTEST", "NSE", "BUY", 10, note="TEST demo")
    assert len(paper_trading.portfolio_summary()["holdings"]) == 1
    out = paper_trading.reset_paper_account()
    assert out["deleted_orders"] == 1
    summary = paper_trading.portfolio_summary()
    assert summary["holdings"] == []
    assert summary["cash"] == paper_trading.DEFAULT_VIRTUAL_CASH
    assert paper_trading.trade_history() == []


def test_order_validation_rejects_bad_sl_target(monkeypatch):
    monkeypatch.setattr(paper_trading, "_latest_price", lambda symbol, exchange: (100.0, "2026-11-19"))
    bad_target = paper_trading.place_order("ZZV", "NSE", "BUY", 1, target=90.0)
    assert not bad_target["ok"] and "target" in bad_target["error"]
    bad_sl = paper_trading.place_order("ZZV", "NSE", "BUY", 1, stop_loss=100.0)
    assert not bad_sl["ok"] and "stop-loss" in bad_sl["error"]
    paper_trading.place_order("ZZV", "NSE", "BUY", 5)
    bad_sell = paper_trading.place_order("ZZV", "NSE", "SELL", 1, target=200.0)
    assert not bad_sell["ok"] and "only apply to BUY" in bad_sell["error"]
    good = paper_trading.place_order("ZZW", "NSE", "BUY", 1, stop_loss=95.0, target=110.0)
    assert good["ok"] and good["gate"]["approved"]


def test_risk_gate_rejects_oversize_and_logs(monkeypatch):
    monkeypatch.setattr(paper_trading, "_latest_price", lambda symbol, exchange: (100.0, "2026-11-19"))
    # cost 500,000 > 25% of 1,000,000 virtual capital (but within cash)
    out = paper_trading.place_order("ZZG", "NSE", "BUY", 5000, note="TEST gate")
    assert not out["ok"]
    assert out["gate"]["status"] == "rejected"
    history = paper_trading.trade_history()
    rejected = [h for h in history if h["risk_status"] == "rejected"]
    assert rejected and "25%" in rejected[0]["risk_reasons"]
    # the rejected order never entered positions
    assert all(h["symbol"] != "ZZG" for h in paper_trading.portfolio_summary()["holdings"])


def test_risk_gate_risk_per_trade_limit(monkeypatch):
    monkeypatch.setattr(paper_trading, "_latest_price", lambda symbol, exchange: (100.0, "2026-11-19"))
    # entry 100, SL 50 -> risk 50/share; 1000 shares -> 50,000 > 2% of 1,000,000 (20,000)
    out = paper_trading.place_order("ZZR", "NSE", "BUY", 1000, stop_loss=50.0)
    assert not out["ok"] and "risk" in out["error"].lower()
    ok = paper_trading.place_order("ZZR", "NSE", "BUY", 100, stop_loss=50.0)
    assert ok["ok"]


def test_floor_activity_running_vs_recent(monkeypatch):
    from datetime import datetime, timezone
    from database.connection import session_scope
    from database.models import AgentRun
    from services import building as building_service
    agent = next(iter(building_service.FLOOR_AGENTS[2]))
    with session_scope() as session:
        session.add(AgentRun(agent_name=agent, status="running",
                             started_at=datetime.now(timezone.utc).replace(tzinfo=None)))
    activity = building_service.floor_activity()
    assert activity[2]["running"] is True
    assert activity[4]["running"] is False  # paper floors never show running
