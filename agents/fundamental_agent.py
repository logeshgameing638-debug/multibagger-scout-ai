"""Agent 2 - Fundamental Analysis.

Computes growth, profitability, balance-sheet, cash-flow and ownership metrics
from stored financial statements. Missing metrics are listed, never invented.
Banks/NBFCs get financial-sector treatment (debt/equity and current-ratio
rules do not apply the same way).
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from data.validation import cagr, safe_div
from .base import AgentResult

AGENT_NAME = "fundamental_analysis"

FINANCIAL_SECTORS = {"financial services", "financials", "banks", "banking"}

# yfinance statement line names (mapped to our canonical metrics)
INCOME_METRICS = {
    "Total Revenue": "revenue",
    "Net Income": "net_profit",
    "Operating Income": "operating_profit",
    "Gross Profit": "gross_profit",
    "Basic EPS": "eps",
    "Diluted EPS": "diluted_eps",
    "Interest Expense": "interest_expense",
    "EBIT": "ebit",
}
BALANCE_METRICS = {
    "Total Debt": "total_debt",
    "Stockholders Equity": "equity",
    "Total Assets": "total_assets",
    "Current Assets": "current_assets",
    "Current Liabilities": "current_liabilities",
    "Cash And Cash Equivalents": "cash",
    "Ordinary Shares Number": "shares_outstanding",
}
CASHFLOW_METRICS = {
    "Operating Cash Flow": "operating_cash_flow",
    "Free Cash Flow": "free_cash_flow",
    "Capital Expenditure": "capex",
}


def _series(statements: dict, statement_type: str, metric: str) -> dict[str, float]:
    """period_end -> value for one metric from a stored statements payload."""
    return {
        period: metrics[metric]
        for period, metrics in statements.get(statement_type, {}).items()
        if metric in metrics
    }


def _latest(series: dict[str, float]) -> float | None:
    if not series:
        return None
    return series[sorted(series)[-1]]


def _value_n_years_ago(series: dict[str, float], years: int) -> float | None:
    """Closest annual reading at least `years` before the latest reading."""
    if not series:
        return None
    dates = sorted(pd.Timestamp(p) for p in series)
    latest = dates[-1]
    target = latest - pd.DateOffset(years=years)
    older = [d for d in dates if d <= target]
    if not older:
        return None
    return series[str(older[-1].date())]


def analyze(
    statements: dict,
    info: dict | None = None,
    sector: str | None = None,
) -> AgentResult:
    """statements: payload from YFinanceConnector.get_financial_statements."""
    result = AgentResult(agent_name=AGENT_NAME, status="success")
    info = info or {}
    is_financial = (sector or info.get("sector") or "").strip().lower() in FINANCIAL_SECTORS

    annual = statements.get("annual", {})
    quarterly = statements.get("quarterly", {})

    revenue = _series(annual, "income", "Total Revenue")
    profit = _series(annual, "income", "Net Income")
    eps = _series(annual, "income", "Basic EPS") or _series(annual, "income", "Diluted EPS")

    growth = {
        "sales_growth_1y": _growth_1y(revenue),
        "sales_cagr_3y": cagr(_value_n_years_ago(revenue, 3), _latest(revenue), 3),
        "sales_cagr_5y": cagr(_value_n_years_ago(revenue, 5), _latest(revenue), 5),
        "profit_growth_1y": _growth_1y(profit),
        "profit_cagr_3y": cagr(_value_n_years_ago(profit, 3), _latest(profit), 3),
        "profit_cagr_5y": cagr(_value_n_years_ago(profit, 5), _latest(profit), 5),
        "eps_growth_1y": _growth_1y(eps),
    }

    equity = _latest(_series(annual, "balance", "Stockholders Equity"))
    total_debt = _latest(_series(annual, "balance", "Total Debt"))
    ebit = _latest(_series(annual, "income", "EBIT"))
    interest_expense = _latest(_series(annual, "income", "Interest Expense"))
    operating_profit = _latest(_series(annual, "income", "Operating Income"))
    gross_profit = _latest(_series(annual, "income", "Gross Profit"))
    latest_revenue = _latest(revenue)
    latest_profit = _latest(profit)
    ocf = _latest(_series(annual, "cashflow", "Operating Cash Flow"))
    fcf = _latest(_series(annual, "cashflow", "Free Cash Flow"))
    current_assets = _latest(_series(annual, "balance", "Current Assets"))
    current_liabilities = _latest(_series(annual, "balance", "Current Liabilities"))

    # Capital employed ~ equity + debt (free-source approximation, labelled).
    capital_employed = None
    if equity is not None and total_debt is not None:
        capital_employed = equity + total_debt

    profitability = {
        "roe": safe_div(latest_profit, equity),
        "roce": safe_div(ebit, capital_employed),
        "operating_margin": safe_div(operating_profit, latest_revenue),
        "net_margin": safe_div(latest_profit, latest_revenue),
        "gross_margin": safe_div(gross_profit, latest_revenue),
    }

    balance_sheet: dict = {
        "total_debt": total_debt,
        "debt_to_equity": safe_div(total_debt, equity),
        "interest_coverage": safe_div(ebit, abs(interest_expense) if interest_expense else None),
        "current_ratio": safe_div(current_assets, current_liabilities),
        "working_capital": (
            current_assets - current_liabilities
            if current_assets is not None and current_liabilities is not None
            else None
        ),
    }

    cash_flow = {
        "operating_cash_flow": ocf,
        "free_cash_flow": fcf,
        "ocf_to_net_profit": safe_div(ocf, latest_profit),
        "fcf_conversion": safe_div(fcf, ocf),
    }

    ownership = {
        "promoter_or_insider_holding_pct": info.get("heldPercentInsiders"),
        "institutional_holding_pct": info.get("heldPercentInstitutions"),
        "promoter_pledge_pct": None,  # not available from free connectors
    }

    red_flags: list[str] = []
    if not is_financial:
        d2e = balance_sheet["debt_to_equity"]
        if d2e is not None and d2e > 1.0:
            red_flags.append(f"debt/equity {d2e:.2f} above 1.0")
    else:
        result.warnings.append(
            "financial-sector company: industrial debt/equity and current-ratio rules not applied"
        )
        balance_sheet["debt_to_equity"] = None
        balance_sheet["current_ratio"] = None
    if ocf is not None and ocf < 0:
        red_flags.append(f"negative operating cash flow ({ocf:,.0f})")
    ocf_np = cash_flow["ocf_to_net_profit"]
    if ocf_np is not None and ocf_np < 0.5 and (latest_profit or 0) > 0:
        red_flags.append(f"operating cash flow only {ocf_np:.0%} of net profit (profit quality)")

    missing = [
        name
        for name, value in {
            **growth, **profitability, **cash_flow,
            "promoter_pledge_pct": None,
        }.items()
        if value is None
    ]
    has_annual_data = any(annual.get(st) for st in ("income", "balance", "cashflow"))
    if not has_annual_data:
        result.status = "failed"
        result.error = "no annual financial statements available"
    elif len(missing) > 8:
        result.status = "partial"

    result.data = {
        "is_financial_sector": is_financial,
        "growth": growth,
        "profitability": profitability,
        "balance_sheet": balance_sheet,
        "cash_flow": cash_flow,
        "ownership": ownership,
        "red_flags": red_flags,
        "annual_periods": sorted(annual.get("income", {}).keys()),
        "quarterly_periods": sorted(quarterly.get("income", {}).keys()),
        "statements": {"annual": annual, "quarterly": quarterly},
    }
    result.missing = missing
    result.sources.append("yahoo_finance")
    return result.finish()


def _growth_1y(series: dict[str, float]) -> float | None:
    if len(series) < 2:
        return None
    dates = sorted(series)
    latest, prior = series[dates[-1]], series[dates[-2]]
    if prior == 0 or prior is None:
        return None
    return (latest - prior) / abs(prior)
