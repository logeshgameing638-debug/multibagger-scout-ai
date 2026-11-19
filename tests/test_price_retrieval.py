"""Price retrieval with a mocked provider: success and honest failure."""
import pandas as pd
import pytest

from data.connectors.yfinance_connector import YFinanceConnector


class _FakeTicker:
    def __init__(self, frame=None, raises=None):
        self._frame = frame
        self._raises = raises

    def history(self, *args, **kwargs):
        if self._raises:
            raise self._raises
        return self._frame


@pytest.fixture()
def connector_no_cache():
    connector = YFinanceConnector()
    return connector


def test_price_success(connector_no_cache, synthetic_ohlcv, monkeypatch):
    monkeypatch.setattr(connector_no_cache, "_ticker", lambda s, e: _FakeTicker(frame=synthetic_ohlcv))
    result = connector_no_cache.get_price("FAKESYM", "NSE", use_cache=False)
    assert result.ok
    assert result.data["close"] == pytest.approx(float(synthetic_ohlcv["close"].iloc[-1]))
    assert result.delayed is True  # delayed data always labelled
    assert result.source == "yahoo_finance"


def test_price_failure_is_honest(connector_no_cache, monkeypatch):
    monkeypatch.setattr(
        connector_no_cache, "_ticker", lambda s, e: _FakeTicker(raises=ConnectionError("provider down"))
    )
    result = connector_no_cache.get_price("FAKESYM", "NSE", use_cache=False)
    assert not result.ok
    assert "provider down" in result.error
    assert result.data is None  # nothing fabricated


def test_empty_history_fails(connector_no_cache, monkeypatch):
    monkeypatch.setattr(connector_no_cache, "_ticker", lambda s, e: _FakeTicker(frame=pd.DataFrame()))
    result = connector_no_cache.get_price("FAKESYM", "NSE", use_cache=False)
    assert not result.ok
    assert result.error


def test_history_returns_validated_frame(connector_no_cache, synthetic_ohlcv, monkeypatch):
    monkeypatch.setattr(connector_no_cache, "_ticker", lambda s, e: _FakeTicker(frame=synthetic_ohlcv))
    result = connector_no_cache.get_history("FAKESYM", "NSE")
    assert result.ok
    assert len(result.data["frame"]) == len(synthetic_ohlcv)
    assert result.data["validation"]["dropped_rows"] == 0


def test_unsupported_exchange():
    with pytest.raises(Exception):
        YFinanceConnector.ticker_symbol("ABC", "LSE")
