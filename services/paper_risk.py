"""Floor 03/04: automated risk gate for SIMULATED paper orders.

Every paper order is evaluated before it fills. REJECTED orders are not
placed; the decision and its reasons are stored on the order row (or
returned to the UI when the order is refused). All of this applies only to
simulated paper trading - no real orders exist.
"""
from __future__ import annotations

from sqlalchemy import desc, select

from database.connection import session_scope
from database.models import AgentOutput, AgentRun, Company

# Gate limits (fraction of total virtual capital: cash + invested)
MAX_POSITION_PCT = 0.25      # one position may not exceed 25% of virtual capital
MAX_RISK_PER_TRADE_PCT = 0.02  # entry-to-stop loss may not risk more than 2%
BLOCKED_RISK_CLASSES = {"HIGH", "CRITICAL"}


def _latest_risk_classification(symbol: str, exchange: str) -> str | None:
    """Most recent stored risk-analysis classification for the company, if any."""
    with session_scope() as session:
        company = session.scalar(
            select(Company).where(Company.symbol == symbol, Company.exchange == exchange))
        if company is None:
            return None
        row = session.execute(
            select(AgentOutput.output_json)
            .join(AgentRun, AgentRun.id == AgentOutput.run_id)
            .where(AgentRun.agent_name == "risk_analysis",
                   AgentOutput.company_id == company.id)
            .order_by(desc(AgentOutput.created_at)).limit(1)
        ).first()
    if not row:
        return None
    import json
    try:
        data = json.loads(row[0] or "{}")
    except ValueError:
        return None
    return (data.get("data") or data).get("classification")


def evaluate_order(symbol: str, exchange: str, side: str, qty: int,
                   price: float, stop_loss: float | None,
                   cash: float, invested: float,
                   existing_cost: float = 0.0) -> dict:
    """Approve or reject a SIMULATED order. Returns {approved, status, reasons, warnings}."""
    reasons: list[str] = []
    warnings: list[str] = []
    total = cash + invested
    cost = price * qty

    if side == "BUY":
        aggregate = existing_cost + cost
        if total > 0 and aggregate > total * MAX_POSITION_PCT:
            reasons.append(
                f"position would total {aggregate:,.2f} "
                f"(existing {existing_cost:,.2f} + new {cost:,.2f}), exceeding "
                f"{MAX_POSITION_PCT:.0%} of virtual capital {total:,.2f}")
        if stop_loss is None:
            warnings.append("no stop-loss supplied - position is unprotected")
        elif stop_loss < price and total > 0:
            risk = (price - stop_loss) * qty
            if risk > total * MAX_RISK_PER_TRADE_PCT:
                reasons.append(
                    f"entry-to-stop risk {risk:,.2f} exceeds {MAX_RISK_PER_TRADE_PCT:.0%} "
                    f"of virtual capital {total:,.2f}")
        classification = _latest_risk_classification(symbol, exchange)
        if classification in BLOCKED_RISK_CLASSES:
            reasons.append(f"stored risk analysis classifies {symbol} as {classification}")
        elif classification is None or classification == "UNASSESSED":
            warnings.append("risk analysis not available for this company - "
                            "gate evaluated exposure and stop rules only")
        else:
            warnings.append(f"stored risk classification: {classification}")
    # SELL (closing a simulated long) is always allowed.

    approved = not reasons
    status = "approved" if approved else "rejected"
    return {"approved": approved, "status": status, "reasons": reasons,
            "warnings": warnings,
            "limits": {"max_position_pct": MAX_POSITION_PCT,
                       "max_risk_per_trade_pct": MAX_RISK_PER_TRADE_PCT}}
