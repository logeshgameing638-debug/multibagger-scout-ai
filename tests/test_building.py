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
    assert all(f["active"] is False for f in floors.values())
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
