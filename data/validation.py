"""Input and OHLCV validation. Never repairs data silently: every dropped or
suspect row is reported in the validation report."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import pandas as pd

# NSE symbols: 1-20 chars of A-Z, 0-9, & and - (e.g. RELIANCE, M&M, BAJAJ-AUTO)
NSE_SYMBOL_RE = re.compile(r"^[A-Z0-9&\-]{1,20}$")
# BSE scrip codes are numeric (commonly 6 digits); alpha symbols also exist.
BSE_SYMBOL_RE = re.compile(r"^(\d{4,6}|[A-Z0-9&\-]{1,20})$")

REQUIRED_OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]


def validate_nse_symbol(symbol: str) -> bool:
    return bool(symbol) and bool(NSE_SYMBOL_RE.match(symbol.strip().upper()))


def validate_bse_symbol(symbol: str) -> bool:
    return bool(symbol) and bool(BSE_SYMBOL_RE.match(symbol.strip().upper()))


@dataclass
class OHLCVReport:
    total_rows: int
    accepted_rows: int
    dropped_rows: int
    issues: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.accepted_rows > 0 and self.dropped_rows == 0


def validate_ohlcv(df: pd.DataFrame) -> tuple[pd.DataFrame, OHLCVReport]:
    """Validate an OHLCV frame (columns open/high/low/close/volume, datetime index).

    Returns (clean_df, report). Rows failing checks are dropped and logged.
    """
    issues: list[str] = []
    if df is None or df.empty:
        return pd.DataFrame(), OHLCVReport(0, 0, 0, ["empty frame"])

    frame = df.copy()
    frame.columns = [str(c).lower() for c in frame.columns]
    missing = [c for c in REQUIRED_OHLCV_COLUMNS if c not in frame.columns]
    if missing:
        return pd.DataFrame(), OHLCVReport(len(df), 0, len(df), [f"missing columns: {missing}"])

    frame = frame.sort_index()
    dupes = int(frame.index.duplicated().sum())
    if dupes:
        issues.append(f"{dupes} duplicate timestamp rows dropped")
        frame = frame[~frame.index.duplicated(keep="last")]

    bad_mask = (
        frame["high"].isna()
        | frame["low"].isna()
        | frame["close"].isna()
        | (frame["high"] < frame["low"])
        | (frame["high"] < frame["open"])
        | (frame["high"] < frame["close"])
        | (frame["low"] > frame["open"])
        | (frame["low"] > frame["close"])
        | (frame["volume"] < 0)
        | (frame[["open", "high", "low", "close"]] <= 0).any(axis=1)
    )
    bad = int(bad_mask.sum())
    if bad:
        issues.append(f"{bad} inconsistent OHLCV rows dropped")
        frame = frame[~bad_mask]

    if not frame.index.is_monotonic_increasing:
        frame = frame.sort_index()

    report = OHLCVReport(
        total_rows=len(df),
        accepted_rows=len(frame),
        dropped_rows=len(df) - len(frame),
        issues=issues,
    )
    return frame, report


def cagr(start_value: float | None, end_value: float | None, years: float) -> float | None:
    """Compound annual growth rate. None when not computable (never invented)."""
    if start_value is None or end_value is None or years <= 0:
        return None
    if start_value <= 0 or end_value <= 0:
        return None  # CAGR undefined across sign changes / zero base
    return (end_value / start_value) ** (1.0 / years) - 1.0


def safe_div(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator
