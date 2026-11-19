"""Agent 3 - Technical Analysis.

All indicators computed from validated OHLCV. Signals use completed candles;
the last (possibly intrabar) candle is labelled provisional when its date is
the current calendar day.
"""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd

from data.validation import validate_ohlcv
from indicators import adx, atr, bollinger_bands, ema, macd, relative_volume, rsi, sma, volume_sma
from .base import AgentResult

AGENT_NAME = "technical_analysis"


def _last(series: pd.Series) -> float | None:
    value = series.iloc[-1] if len(series) else None
    return float(value) if value is not None and pd.notna(value) else None


def _swing_levels(frame: pd.DataFrame, lookback: int = 60) -> dict:
    window = frame.tail(lookback)
    if window.empty:
        return {"support": None, "resistance": None}
    recent_close = float(frame["close"].iloc[-1])
    lows = window["low"]
    highs = window["high"]
    support = float(lows.min())
    resistance = float(highs.max())
    # Refine: nearest swing low/high around price rather than absolute extremes.
    below = window[window["low"] < recent_close]
    above = window[window["high"] > recent_close]
    if not below.empty:
        support = float(below["low"].tail(20).min())
    if not above.empty:
        resistance = float(above["high"].tail(20).max())
    return {"support": support, "resistance": resistance}


def _price_structure(frame: pd.DataFrame, lookback: int = 60) -> dict:
    """Detect higher highs / higher lows vs lower highs / lower lows using
    two halves of the lookback window."""
    window = frame.tail(lookback)
    if len(window) < 10:
        return {"structure": "insufficient_data"}
    half = len(window) // 2
    first, second = window.iloc[:half], window.iloc[half:]
    higher_highs = second["high"].max() > first["high"].max()
    higher_lows = second["low"].min() > first["low"].min()
    lower_highs = second["high"].max() < first["high"].max()
    lower_lows = second["low"].min() < first["low"].min()
    if higher_highs and higher_lows:
        structure = "uptrend (higher highs, higher lows)"
    elif lower_highs and lower_lows:
        structure = "downtrend (lower highs, lower lows)"
    else:
        structure = "consolidation / mixed"
    return {
        "structure": structure,
        "higher_highs": bool(higher_highs),
        "higher_lows": bool(higher_lows),
        "lower_highs": bool(lower_highs),
        "lower_lows": bool(lower_lows),
    }


def analyze_frame(frame: pd.DataFrame, timeframe: str = "1d") -> dict:
    """Core computation shared by all timeframes. Returns the report dict."""
    close, high, low, volume = frame["close"], frame["high"], frame["low"], frame["volume"]

    emas = {f"ema_{n}": ema(close, n) for n in (20, 50, 100, 200)}
    smas = {f"sma_{n}": sma(close, n) for n in (20, 50, 100, 200)}
    rsi14 = rsi(close, 14)
    macd_line, signal_line, histogram = macd(close)
    adx14 = adx(high, low, close, 14)
    atr14 = atr(high, low, close, 14)
    bb_mid, bb_up, bb_low = bollinger_bands(close, 20, 2.0)
    vol_sma20 = volume_sma(volume, 20)
    rel_vol = relative_volume(volume, 20)

    last_close = float(close.iloc[-1])
    levels = _swing_levels(frame)
    structure = _price_structure(frame)

    ema_values = {k: _last(v) for k, v in emas.items()}
    aligned_bull = all(
        v is not None for v in ema_values.values()
    ) and last_close > ema_values["ema_20"] > ema_values["ema_50"] > ema_values["ema_100"] > ema_values["ema_200"]  # type: ignore[operator]
    aligned_bear = all(
        v is not None for v in ema_values.values()
    ) and last_close < ema_values["ema_20"] < ema_values["ema_50"] < ema_values["ema_100"] < ema_values["ema_200"]  # type: ignore[operator]

    last_rsi = _last(rsi14)
    last_adx = _last(adx14)
    last_atr = _last(atr14)
    last_hist = _last(histogram)
    last_rel_vol = _last(rel_vol)

    # Breakout: close above resistance with above-average volume (completed candle).
    breakout = False
    breakdown = False
    if levels["resistance"] is not None and last_close > levels["resistance"]:
        breakout = bool(last_rel_vol is not None and last_rel_vol >= 1.2)
    if levels["support"] is not None and last_close < levels["support"]:
        breakdown = True

    # Momentum divergence: price makes new 60-bar high while RSI does not.
    divergence = None
    if len(frame) >= 60 and rsi14.notna().sum() >= 30:
        recent = frame.tail(60)
        price_high_now = recent["close"].idxmax() == frame.index[-1]
        rsi_recent = rsi14.reindex(recent.index)
        if price_high_now and float(rsi_recent.max()) > float(rsi14.iloc[-1]):
            divergence = "possible bearish divergence (price new high, RSI lower high)"

    if aligned_bull:
        trend = "bullish"
    elif aligned_bear:
        trend = "bearish"
    else:
        trend = "sideways"

    atr_distance = last_atr
    entry_zone = None
    invalidation = None
    if levels["support"] is not None and last_atr is not None:
        entry_zone = {
            "low": round(levels["support"], 2),
            "high": round(levels["support"] + 0.5 * last_atr, 2),
            "basis": "near identified support plus half ATR buffer",
        }
        invalidation = round(levels["support"] - 2.0 * last_atr, 2)

    return {
        "timeframe": timeframe,
        "last_close": last_close,
        "emas": ema_values,
        "smas": {k: _last(v) for k, v in smas.items()},
        "rsi_14": last_rsi,
        "macd": {
            "macd_line": _last(macd_line),
            "signal_line": _last(signal_line),
            "histogram": last_hist,
        },
        "adx_14": last_adx,
        "atr_14": last_atr,
        "bollinger": {"middle": _last(bb_mid), "upper": _last(bb_up), "lower": _last(bb_low)},
        "volume_sma_20": _last(vol_sma20),
        "relative_volume": last_rel_vol,
        "support": levels["support"],
        "resistance": levels["resistance"],
        "price_structure": structure,
        "trend": trend,
        "trend_strength": ("strong" if (last_adx or 0) >= 25 else "weak") if last_adx else None,
        "breakout": breakout,
        "breakdown": breakdown,
        "momentum_divergence": divergence,
        "entry_zone": entry_zone,
        "invalidation_level": invalidation,
        "atr_risk_distance": atr_distance,
    }


def analyze(history: pd.DataFrame) -> AgentResult:
    """Full multi-timeframe technical report from a daily OHLCV frame."""
    result = AgentResult(agent_name=AGENT_NAME, status="success")
    if history is None or history.empty:
        result.status = "failed"
        result.error = "no OHLCV history supplied"
        return result.finish()

    frame, report = validate_ohlcv(history)
    if report.dropped_rows:
        result.warnings.append(f"OHLCV validation dropped {report.dropped_rows} rows: {report.issues}")
    if len(frame) < 30:
        result.status = "failed"
        result.error = f"insufficient history ({len(frame)} valid rows)"
        return result.finish()

    # Completed-candle labelling: last bar is provisional if dated today.
    last_date = pd.Timestamp(frame.index[-1]).date()
    provisional = last_date >= datetime.now(timezone.utc).date()

    daily = analyze_frame(frame, "1d")
    daily["provisional_last_bar"] = provisional

    weekly_frame = frame.resample("W").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    ).dropna()
    monthly_frame = frame.resample("ME").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    ).dropna()

    weekly = analyze_frame(weekly_frame, "1w") if len(weekly_frame) >= 30 else None
    monthly = analyze_frame(monthly_frame, "1M") if len(monthly_frame) >= 24 else None

    long_term_trend = (monthly or weekly or daily)["trend"]

    result.data = {
        "daily": daily,
        "weekly": weekly,
        "monthly": monthly,
        "short_term_report": {
            "timeframe": "daily",
            "trend": daily["trend"],
            "rsi_14": daily["rsi_14"],
            "macd_histogram": daily["macd"]["histogram"],
            "breakout": daily["breakout"],
            "breakdown": daily["breakdown"],
        },
        "long_term_report": {
            "timeframes": ["weekly", "monthly"],
            "trend": long_term_trend,
            "ema_200_daily": daily["emas"]["ema_200"],
            "price_vs_ema_200": (
                "above" if daily["emas"]["ema_200"] and daily["last_close"] > daily["emas"]["ema_200"]
                else "below" if daily["emas"]["ema_200"] else None
            ),
        },
        "assessment": daily["trend"],
        "entry_zone": daily["entry_zone"],
        "invalidation_level": daily["invalidation_level"],
        "atr_risk_distance": daily["atr_risk_distance"],
        "rows_used": len(frame),
    }
    if weekly is None:
        result.missing.append("weekly timeframe (insufficient history)")
    if monthly is None:
        result.missing.append("monthly timeframe (insufficient history)")
    if provisional:
        result.warnings.append(
            "most recent daily bar is intraday/provisional; confirmed signals use completed candles"
        )
    result.sources.append("yahoo_finance")
    return result.finish()
