"""Shared synthetic fixtures.

IMPORTANT: every frame/statement here is SYNTHETIC test data. It is never
presented as real market data, and no test touches the network.
"""
from __future__ import annotations

import os
import tempfile

import numpy as np
import pandas as pd
import pytest

# Point the app at a throwaway SQLite file before any project import.
_TMP_DB = os.path.join(tempfile.mkdtemp(prefix="mbai_test_"), "test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB}"
os.environ.setdefault("EXPORTS_TEST_DIR", tempfile.mkdtemp(prefix="mbai_exports_"))


@pytest.fixture()
def synthetic_ohlcv() -> pd.DataFrame:
    """300 business days of a synthetic, gently uptrending series."""
    rng = np.random.default_rng(42)
    n = 300
    drift = np.linspace(100, 160, n)
    noise = rng.normal(0, 1.5, n).cumsum() * 0.2
    close = drift + noise
    open_ = close + rng.normal(0, 0.4, n)
    high = np.maximum(open_, close) + rng.uniform(0.2, 1.0, n)
    low = np.minimum(open_, close) - rng.uniform(0.2, 1.0, n)
    volume = rng.uniform(1e5, 3e5, n)
    index = pd.bdate_range("2023-01-02", periods=n)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=index,
    )


@pytest.fixture()
def synthetic_statements() -> dict:
    """Four annual periods of synthetic statements with steady growth."""
    years = ["2021-03-31", "2022-03-31", "2023-03-31", "2024-03-31"]
    revenue = [100e7, 115e7, 132e7, 152e7]
    profit = [10e7, 12e7, 14.5e7, 17e7]
    equity = [50e7, 58e7, 68e7, 80e7]
    income, balance, cashflow = {}, {}, {}
    for i, period in enumerate(years):
        income[period] = {
            "Total Revenue": revenue[i],
            "Net Income": profit[i],
            "Operating Income": profit[i] * 1.3,
            "Gross Profit": revenue[i] * 0.42,
            "Basic EPS": 10 + i * 2.0,
            "EBIT": profit[i] * 1.35,
            "Interest Expense": -1e7,
        }
        balance[period] = {
            "Total Debt": 8e7,
            "Stockholders Equity": equity[i],
            "Total Assets": equity[i] + 8e7 + 20e7,
            "Current Assets": 40e7,
            "Current Liabilities": 25e7,
            "Ordinary Shares Number": 1e7,
        }
        cashflow[period] = {
            "Operating Cash Flow": profit[i] * 1.2,
            "Free Cash Flow": profit[i] * 0.9,
            "Capital Expenditure": -2e7,
        }
    return {
        "annual": {"income": income, "balance": balance, "cashflow": cashflow},
        "quarterly": {"income": {}, "balance": {}, "cashflow": {}},
    }


@pytest.fixture()
def synthetic_info() -> dict:
    return {
        "longName": "Synthetic Test Industries",
        "sector": "Industrials",
        "industry": "Test Machinery",
        "marketCap": 1.5e10,
        "trailingPE": 22.0,
        "priceToBook": 3.1,
        "enterpriseToEbitda": 14.0,
        "dividendYield": 0.008,
        "beta": 1.05,
        "heldPercentInsiders": 0.55,
        "heldPercentInstitutions": 0.25,
        "sharesOutstanding": 1e7,
        "fiftyTwoWeekHigh": 180.0,
        "fiftyTwoWeekLow": 95.0,
    }
