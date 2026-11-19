"""Provider rate-limit handling: cached health probes with 429 backoff, and
rotation batches that stop instead of amplifying throttling."""
from unittest import mock

from data.connectors.yfinance_connector import YFinanceConnector
from data.connectors.base import ConnectorResult
import scripts.daily_update as du
from services.report_view import format_entry_zone


def _reset(conn_cls=YFinanceConnector):
    conn_cls._health_checked_at = 0.0
    conn_cls._health_ok = False
    conn_cls._health_error = None
    conn_cls._health_backoff_until = 0.0


def test_health_check_cached_within_ttl():
    _reset()
    conn = YFinanceConnector()
    with mock.patch.object(YFinanceConnector, "get_price",
                           return_value=ConnectorResult(ok=True, source="yahoo_finance")) as gp:
        assert conn.health_check().ok
        assert conn.health_check().ok
    assert gp.call_count == 1  # second render reused the cached probe


def test_health_check_429_triggers_backoff():
    _reset()
    conn = YFinanceConnector()
    with mock.patch.object(YFinanceConnector, "get_price",
                           return_value=ConnectorResult(ok=False, source="yahoo_finance",
                                                        error="HTTP 429 Too Many Requests")) as gp:
        assert not conn.health_check().ok
        # during backoff no further live probe is made
        result = conn.health_check()
        assert not result.ok
    assert gp.call_count == 1
    assert YFinanceConnector._health_backoff_until > 0


def test_retry_after_hint_respected():
    secs = YFinanceConnector._retry_after_seconds("HTTP 429, Retry-After: 120", 3600)
    assert secs == 120.0
    assert YFinanceConnector._retry_after_seconds("HTTP 429", 3600) == 3600


def test_batch_stops_on_sustained_rate_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(du, "ROOT", tmp_path)
    monkeypatch.setattr(du, "SNAPSHOT_DIR", tmp_path / "snaps")
    monkeypatch.setattr(du, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(du, "BSE_UNIVERSE_CSV", tmp_path / "no_bse.csv")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "universe_nse_part1.csv").write_text(
        "symbol,name,isin\n" + "".join(f"S{i:03},Co{i},\n" for i in range(12)))

    calls = []

    def always_limited(symbol, exchange="NSE"):
        calls.append(symbol)
        return {"symbol": symbol, "exchange": exchange, "status": "system_error",
                "error": "HTTP 429 Too Many Requests", "updated_at": "2026-11-19 20:00 IST"}

    state = du.run_batch(batch_size=12, time_budget_minutes=5, sleep_seconds=0,
                         researcher=always_limited)
    assert len(calls) == du.RATE_LIMIT_STOP_AFTER  # stopped early
    assert "rate limiting" in state["last_run_stopped_reason"]
    assert state["last_run"]["skipped_time_budget"] == 12 - du.RATE_LIMIT_STOP_AFTER


def test_batch_tolerates_isolated_rate_limits(tmp_path, monkeypatch):
    monkeypatch.setattr(du, "ROOT", tmp_path)
    monkeypatch.setattr(du, "SNAPSHOT_DIR", tmp_path / "snaps")
    monkeypatch.setattr(du, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(du, "BSE_UNIVERSE_CSV", tmp_path / "no_bse.csv")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "universe_nse_part1.csv").write_text(
        "symbol,name,isin\n" + "".join(f"S{i:03},Co{i},\n" for i in range(6)))

    def flaky(symbol, exchange="NSE"):
        if symbol in ("S001", "S004"):
            return {"symbol": symbol, "exchange": exchange, "status": "system_error",
                    "error": "HTTP 429", "updated_at": "x"}
        return {"symbol": symbol, "exchange": exchange, "status": "complete", "updated_at": "x"}

    state = du.run_batch(batch_size=6, time_budget_minutes=5, sleep_seconds=0, researcher=flaky)
    assert "last_run_stopped_reason" not in state
    assert state["last_run"]["attempted"] == 6


def test_entry_zone_rupee_formatting():
    assert format_entry_zone({"low": 545.0, "high": 557.75,
                              "basis": "near support"}) == "\u20B9545.00 - \u20B9557.75 (near support)"
    assert format_entry_zone(None) == ""
    assert format_entry_zone({"low": 100.0}) == "from \u20B9100.00"
