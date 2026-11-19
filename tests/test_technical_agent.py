"""Technical agent end-to-end on synthetic data."""
from agents import technical_agent


def test_analyze_synthetic_uptrend(synthetic_ohlcv):
    result = technical_agent.analyze(synthetic_ohlcv)
    assert result.status == "success"
    daily = result.data["daily"]
    assert daily["trend"] in {"bullish", "sideways", "bearish"}
    assert daily["rsi_14"] is not None
    assert daily["emas"]["ema_200"] is not None
    assert daily["support"] is not None and daily["resistance"] is not None
    assert daily["support"] < daily["resistance"]
    assert result.data["rows_used"] == len(synthetic_ohlcv)


def test_insufficient_history_fails():
    import numpy as np
    import pandas as pd

    frame = pd.DataFrame(
        {"open": [10.0] * 10, "high": [11.0] * 10, "low": [9.0] * 10,
         "close": [10.0] * 10, "volume": [100.0] * 10},
        index=pd.bdate_range("2024-01-01", periods=10),
    )
    result = technical_agent.analyze(frame)
    assert result.status == "failed"
    assert "insufficient" in result.error


def test_invalid_ohlcv_rows_reported(synthetic_ohlcv):
    broken = synthetic_ohlcv.copy()
    broken.iloc[5, broken.columns.get_loc("high")] = broken["low"].iloc[5] - 1
    result = technical_agent.analyze(broken)
    assert any("dropped" in w for w in result.warnings)
