"""Trend indicators: SMA, EMA, MACD, ADX (Wilder)."""
from __future__ import annotations

import numpy as np
import pandas as pd


def sma(series: pd.Series, window: int) -> pd.Series:
    if window <= 0:
        raise ValueError("window must be positive")
    return series.rolling(window=window, min_periods=window).mean()


def ema(series: pd.Series, window: int) -> pd.Series:
    if window <= 0:
        raise ValueError("window must be positive")
    return series.ewm(span=window, adjust=False, min_periods=window).mean()


def macd(
    close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Returns (macd_line, signal_line, histogram)."""
    macd_line = ema(close, fast) - ema(close, slow)
    signal_line = macd_line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def _wilder_smooth(series: pd.Series, window: int) -> pd.Series:
    """Wilder's smoothing == EMA with alpha = 1/window."""
    return series.ewm(alpha=1.0 / window, adjust=False, min_periods=window).mean()


def adx(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.Series:
    """Average Directional Index (Wilder). Returns the ADX series."""
    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = pd.Series(
        np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=high.index
    )
    minus_dm = pd.Series(
        np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=high.index
    )

    prev_close = close.shift(1)
    true_range = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)

    atr_series = _wilder_smooth(true_range, window)
    with np.errstate(divide="ignore", invalid="ignore"):
        plus_di = 100.0 * _wilder_smooth(plus_dm, window) / atr_series
        minus_di = 100.0 * _wilder_smooth(minus_dm, window) / atr_series
        dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    return _wilder_smooth(dx, window)
