"""Indicator calculations against hand-computed/known values."""
import numpy as np
import pandas as pd
import pytest

from indicators import adx, atr, bollinger_bands, ema, macd, rsi, sma


class TestEMA:
    def test_hand_computed(self):
        series = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        result = ema(series, 3)
        # k = 0.5, adjust=False: 1, 1.5, 2.25, 3.125, 4.0625 with min_periods=3
        assert np.isnan(result.iloc[0]) and np.isnan(result.iloc[1])
        assert result.iloc[2] == pytest.approx(2.25)
        assert result.iloc[3] == pytest.approx(3.125)
        assert result.iloc[4] == pytest.approx(4.0625)

    def test_constant_series(self):
        result = ema(pd.Series([7.0] * 50), 10)
        assert result.iloc[-1] == pytest.approx(7.0)


class TestSMA:
    def test_values(self):
        result = sma(pd.Series([1.0, 2.0, 3.0, 4.0, 5.0]), 3)
        assert result.iloc[2] == pytest.approx(2.0)
        assert result.iloc[4] == pytest.approx(4.0)


class TestRSI:
    def test_all_gains_is_100(self):
        result = rsi(pd.Series(np.arange(1.0, 40.0)), 14)
        assert result.iloc[-1] == pytest.approx(100.0)

    def test_all_losses_is_0(self):
        result = rsi(pd.Series(np.arange(40.0, 1.0, -1.0)), 14)
        assert result.iloc[-1] == pytest.approx(0.0)

    def test_flat_is_50(self):
        result = rsi(pd.Series([10.0] * 40), 14)
        assert result.iloc[-1] == pytest.approx(50.0)

    def test_range(self, synthetic_ohlcv):
        result = rsi(synthetic_ohlcv["close"], 14).dropna()
        assert ((result >= 0) & (result <= 100)).all()


class TestMACD:
    def test_constant_series_zero(self):
        line, signal, hist = macd(pd.Series([50.0] * 100))
        assert line.iloc[-1] == pytest.approx(0.0)
        assert hist.iloc[-1] == pytest.approx(0.0)

    def test_uptrend_positive(self, synthetic_ohlcv):
        line, signal, hist = macd(synthetic_ohlcv["close"])
        assert line.iloc[-1] > 0  # rising series -> fast EMA above slow EMA


class TestATR:
    def test_constant_ranges(self):
        n = 50
        frame = pd.DataFrame(
            {"high": [11.0] * n, "low": [9.0] * n, "close": [10.0] * n}
        )
        result = atr(frame["high"], frame["low"], frame["close"], 14)
        assert result.iloc[-1] == pytest.approx(2.0)


class TestADX:
    def test_strong_uptrend_high_adx(self):
        n = 120
        close = pd.Series(np.linspace(100, 200, n))
        high = close + 1.0
        low = close - 1.0
        result = adx(high, low, close, 14)
        assert result.iloc[-1] > 25
        assert 0 <= result.iloc[-1] <= 100

    def test_output_bounded(self, synthetic_ohlcv):
        result = adx(synthetic_ohlcv["high"], synthetic_ohlcv["low"], synthetic_ohlcv["close"]).dropna()
        assert ((result >= 0) & (result <= 100)).all()


class TestBollinger:
    def test_band_order(self, synthetic_ohlcv):
        mid, up, low = bollinger_bands(synthetic_ohlcv["close"])
        valid = (mid.notna()) & (up.notna()) & (low.notna())
        assert (up[valid] >= mid[valid]).all()
        assert (mid[valid] >= low[valid]).all()
