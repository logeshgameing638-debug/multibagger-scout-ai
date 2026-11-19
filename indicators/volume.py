"""Volume indicators: volume SMA, relative volume, VWAP."""
from __future__ import annotations

import pandas as pd


def volume_sma(volume: pd.Series, window: int = 20) -> pd.Series:
    return volume.rolling(window=window, min_periods=window).mean()


def relative_volume(volume: pd.Series, window: int = 20) -> pd.Series:
    """Current volume relative to its own rolling average (ratio)."""
    avg = volume_sma(volume, window)
    return volume / avg


def vwap(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series) -> pd.Series:
    """Cumulative VWAP over the supplied window of rows.

    For session-anchored VWAP, pass a single session's rows.
    """
    typical_price = (high + low + close) / 3.0
    cumulative_pv = (typical_price * volume).cumsum()
    cumulative_volume = volume.cumsum()
    return cumulative_pv / cumulative_volume.replace(0, pd.NA)
