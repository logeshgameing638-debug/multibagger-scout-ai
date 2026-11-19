"""Historical OHLCV validation."""
import numpy as np
import pandas as pd

from data.validation import validate_ohlcv


def test_clean_frame_passes(synthetic_ohlcv):
    clean, report = validate_ohlcv(synthetic_ohlcv)
    assert report.ok
    assert report.accepted_rows == len(synthetic_ohlcv)


def test_high_below_low_dropped():
    frame = pd.DataFrame(
        {"open": [10.0], "high": [9.0], "low": [9.5], "close": [9.8], "volume": [100.0]},
        index=pd.to_datetime(["2024-01-02"]),
    )
    clean, report = validate_ohlcv(frame)
    assert clean.empty
    assert report.dropped_rows == 1
    assert report.issues


def test_negative_volume_and_zero_price_dropped():
    index = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])
    frame = pd.DataFrame(
        {
            "open": [10.0, 10.0, 0.0],
            "high": [11.0, 11.0, 0.0],
            "low": [9.0, 9.0, 0.0],
            "close": [10.5, 10.5, 0.0],
            "volume": [100.0, -5.0, 100.0],
        },
        index=index,
    )
    clean, report = validate_ohlcv(frame)
    assert report.accepted_rows == 1
    assert report.dropped_rows == 2


def test_duplicate_timestamps_dropped():
    index = pd.to_datetime(["2024-01-02", "2024-01-02"])
    frame = pd.DataFrame(
        {"open": [10.0, 10.1], "high": [11.0, 11.1], "low": [9.0, 9.1],
         "close": [10.5, 10.6], "volume": [100.0, 200.0]},
        index=index,
    )
    clean, report = validate_ohlcv(frame)
    assert report.accepted_rows == 1
    assert any("duplicate" in issue for issue in report.issues)


def test_missing_columns_reported():
    frame = pd.DataFrame({"open": [1.0], "close": [1.0]}, index=pd.to_datetime(["2024-01-02"]))
    clean, report = validate_ohlcv(frame)
    assert clean.empty
    assert any("missing columns" in issue for issue in report.issues)


def test_empty_frame():
    clean, report = validate_ohlcv(pd.DataFrame())
    assert clean.empty and not report.ok
