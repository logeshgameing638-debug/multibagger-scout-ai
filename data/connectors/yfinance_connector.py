"""Yahoo Finance connector via yfinance (unofficial, free, no key).

yfinance data can be delayed (typically ~15 min for NSE) and occasionally
missing fields. Everything returned carries source + retrieval time, and
failures raise ConnectorError instead of fabricating values.
"""
from __future__ import annotations

import time
from typing import Any

import pandas as pd

from config import get_settings
from data.cache import cache_get, cache_set
from data.validation import validate_ohlcv
from .base import BaseConnector, ConnectorError, ConnectorResult

EXCHANGE_SUFFIX = {"NSE": ".NS", "BSE": ".BO"}


class YFinanceConnector(BaseConnector):
    name = "yahoo_finance"
    type = "prices+fundamentals"
    base_url = "https://finance.yahoo.com"

    @staticmethod
    def ticker_symbol(symbol: str, exchange: str) -> str:
        suffix = EXCHANGE_SUFFIX.get(exchange.upper())
        if suffix is None:
            raise ConnectorError(f"unsupported exchange: {exchange}")
        return f"{symbol.upper()}{suffix}"

    def _ticker(self, symbol: str, exchange: str):
        import yfinance as yf

        return yf.Ticker(self.ticker_symbol(symbol, exchange))

    # Process-level health cache: the app header probes health on every page
    # render, and each probe hits Yahoo. Cache the answer so renders reuse it,
    # and after a rate-limit (HTTP 429) stop probing for the backoff window
    # instead of amplifying the throttling.
    _health_checked_at = 0.0
    _health_ok = False
    _health_error: str | None = None
    _health_backoff_until = 0.0
    HEALTH_TTL_SECONDS = 1800  # at most one real probe per 30 min per process
    HEALTH_RATE_LIMIT_BACKOFF_SECONDS = 3600

    @staticmethod
    def _is_rate_limited(error: str | None) -> bool:
        if not error:
            return False
        text = error.lower()
        return "429" in text or "too many requests" in text or "rate limit" in text

    @staticmethod
    def _retry_after_seconds(error: str | None, default: float) -> float:
        """Honor a Retry-After hint when the provider's error carries one."""
        if error:
            import re
            match = re.search(r"retry[- ]after[:\s]+(\d+)", error, re.IGNORECASE)
            if match:
                try:
                    return max(float(match.group(1)), 60.0)
                except ValueError:
                    pass
        return default

    def health_check(self) -> ConnectorResult:
        now = time.time()
        if now < self._health_backoff_until:
            return ConnectorResult(ok=False, source=self.name,
                                   error=self._health_error or "rate-limit backoff active")
        if now - self._health_checked_at < self.HEALTH_TTL_SECONDS:
            return ConnectorResult(ok=self._health_ok, source=self.name,
                                   error=self._health_error)
        try:
            result = self.get_price("RELIANCE", "NSE", use_cache=False)
            type(self)._health_checked_at = now
            type(self)._health_ok = result.ok
            type(self)._health_error = result.error
            if not result.ok and self._is_rate_limited(result.error):
                type(self)._health_backoff_until = now + self._retry_after_seconds(
                    result.error, self.HEALTH_RATE_LIMIT_BACKOFF_SECONDS)
            self.record_health(result.ok, result.error)
            return result
        except Exception as exc:
            type(self)._health_checked_at = now
            type(self)._health_ok = False
            type(self)._health_error = str(exc)
            if self._is_rate_limited(str(exc)):
                type(self)._health_backoff_until = now + self._retry_after_seconds(
                    str(exc), self.HEALTH_RATE_LIMIT_BACKOFF_SECONDS)
            self.record_health(False, str(exc))
            return ConnectorResult(ok=False, source=self.name, error=str(exc))

    def get_price(self, symbol: str, exchange: str, use_cache: bool = True) -> ConnectorResult:
        """Latest daily close (and session stats). Delayed data is labelled."""
        cache_key = f"yf:price:{exchange}:{symbol}"
        if use_cache:
            cached = cache_get(cache_key, get_settings().price_cache_ttl_minutes)
            if cached:
                payload, stored_at = cached
                return ConnectorResult(
                    ok=True, source=self.name, data=payload, retrieved_at=stored_at,
                    from_cache=True, delayed=True,
                )
        try:
            ticker = self._ticker(symbol, exchange)
            history = ticker.history(period="5d", interval="1d")
            if history is None or history.empty:
                raise ConnectorError(f"no price history returned for {symbol} ({exchange})")
            history, report = validate_ohlcv(history)
            if history.empty:
                raise ConnectorError(f"price history failed validation: {report.issues}")
            last = history.iloc[-1]
            payload = {
                "symbol": symbol.upper(),
                "exchange": exchange.upper(),
                "close": float(last["close"]),
                "open": float(last["open"]),
                "high": float(last["high"]),
                "low": float(last["low"]),
                "volume": float(last["volume"]),
                "as_of": str(history.index[-1]),
                "note": "Yahoo Finance NSE/BSE quotes are typically delayed ~15 minutes",
            }
            cache_set(cache_key, payload)
            self.record_health(True)
            return ConnectorResult(ok=True, source=self.name, data=payload, delayed=True)
        except Exception as exc:
            self.record_health(False, str(exc))
            return ConnectorResult(ok=False, source=self.name, error=str(exc))

    def get_history(
        self, symbol: str, exchange: str, period: str = "5y", interval: str = "1d"
    ) -> ConnectorResult:
        """Historical OHLCV. Validated; invalid rows dropped and reported."""
        try:
            ticker = self._ticker(symbol, exchange)
            history = ticker.history(period=period, interval=interval, auto_adjust=False)
            if history is None or history.empty:
                raise ConnectorError(f"no history for {symbol} ({exchange})")
            history, report = validate_ohlcv(history)
            self.record_health(True)
            return ConnectorResult(
                ok=True,
                source=self.name,
                data={"frame": history, "validation": report.__dict__, "delayed": True},
                delayed=True,
            )
        except Exception as exc:
            self.record_health(False, str(exc))
            return ConnectorResult(ok=False, source=self.name, error=str(exc))

    def get_info(self, symbol: str, exchange: str) -> ConnectorResult:
        """Company profile + snapshot ratios. Missing fields stay missing."""
        try:
            info: dict[str, Any] = self._ticker(symbol, exchange).info or {}
            keys = [
                "longName", "sector", "industry", "marketCap", "trailingPE", "forwardPE",
                "priceToBook", "enterpriseToEbitda", "enterpriseToRevenue", "pegRatio",
                "dividendYield", "beta", "returnOnEquity", "profitMargins",
                "operatingMargins", "grossMargins", "debtToEquity", "currentRatio",
                "totalDebt", "totalCash", "freeCashflow", "operatingCashflow",
                "heldPercentInsiders", "heldPercentInstitutions", "sharesOutstanding",
                "bookValue", "trailingEps", "forwardEps", "fiftyTwoWeekHigh",
                "fiftyTwoWeekLow", "currency", "website",
            ]
            payload = {k: info.get(k) for k in keys if info.get(k) is not None}
            if not payload:
                raise ConnectorError(f"no info returned for {symbol} ({exchange})")
            self.record_health(True)
            return ConnectorResult(ok=True, source=self.name, data=payload)
        except Exception as exc:
            self.record_health(False, str(exc))
            return ConnectorResult(ok=False, source=self.name, error=str(exc))

    def get_financial_statements(self, symbol: str, exchange: str) -> ConnectorResult:
        """Annual + quarterly income statement, balance sheet and cash flow.

        Returns raw frames mapped into {statement_type: {period_end: {metric: value}}}.
        """
        try:
            ticker = self._ticker(symbol, exchange)
            frames: dict[str, dict[str, pd.DataFrame]] = {
                "annual": {
                    "income": ticker.financials,
                    "balance": ticker.balance_sheet,
                    "cashflow": ticker.cashflow,
                },
                "quarterly": {
                    "income": ticker.quarterly_financials,
                    "balance": ticker.quarterly_balance_sheet,
                    "cashflow": ticker.quarterly_cashflow,
                },
            }
            payload: dict[str, dict[str, dict[str, dict[str, float]]]] = {}
            found_any = False
            for period_type, statements in frames.items():
                payload[period_type] = {}
                for statement_type, frame in statements.items():
                    mapped: dict[str, dict[str, float]] = {}
                    if isinstance(frame, pd.DataFrame) and not frame.empty:
                        found_any = True
                        for column in frame.columns:
                            period_end = str(pd.Timestamp(column).date())
                            metrics: dict[str, float] = {}
                            for metric, value in frame[column].items():
                                if pd.notna(value):
                                    metrics[str(metric)] = float(value)
                            if metrics:
                                mapped[period_end] = metrics
                    payload[period_type][statement_type] = mapped
            if not found_any:
                raise ConnectorError(f"no financial statements for {symbol} ({exchange})")
            self.record_health(True)
            return ConnectorResult(ok=True, source=self.name, data=payload)
        except Exception as exc:
            self.record_health(False, str(exc))
            return ConnectorResult(ok=False, source=self.name, error=str(exc))
