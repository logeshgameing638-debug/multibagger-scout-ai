"""Alerts service: technical thresholds, score changes, risk escalation.

Alerts are rows in the database shown on the Alerts page. No notification is
faked as sent: delivery is the dashboard itself.
"""
from __future__ import annotations

from sqlalchemy import select

from database.connection import session_scope
from database.models import Alert, Company, ResearchScore


def create_alert(company_id: int | None, alert_type: str, message: str,
                 severity: str = "info", triggered_value: float | None = None,
                 threshold: float | None = None) -> int:
    with session_scope() as session:
        alert = Alert(
            company_id=company_id, alert_type=alert_type, message=message,
            severity=severity, triggered_value=triggered_value, threshold=threshold,
        )
        session.add(alert)
        session.flush()
        return alert.id


def list_alerts(status: str | None = "open", limit: int = 200) -> list[dict]:
    with session_scope() as session:
        query = select(Alert, Company.symbol).join(
            Company, Company.id == Alert.company_id, isouter=True
        ).order_by(Alert.created_at.desc()).limit(limit)
        if status:
            query = query.where(Alert.status == status)
        return [
            {
                "id": alert.id,
                "symbol": symbol,
                "type": alert.alert_type,
                "message": alert.message,
                "severity": alert.severity,
                "status": alert.status,
                "created_at": str(alert.created_at),
            }
            for alert, symbol in session.execute(query).all()
        ]


def acknowledge(alert_id: int) -> bool:
    with session_scope() as session:
        alert = session.get(Alert, alert_id)
        if alert is None:
            return False
        alert.status = "acknowledged"
        return True


def check_technical_thresholds() -> int:
    """Alert on RSI extremes, breakouts and breakdowns from the latest
    technical agent output per company. Returns alerts created."""
    import json

    from database.models import AgentOutput, AgentRun

    created = 0
    with session_scope() as session:
        rows = session.execute(
            select(AgentOutput, Company.symbol)
            .join(AgentRun, AgentRun.id == AgentOutput.run_id)
            .join(Company, Company.id == AgentOutput.company_id)
            .where(AgentRun.agent_name == "technical_analysis")
            .order_by(AgentOutput.created_at.desc())
        ).all()
        seen: set[int] = set()
        for output, symbol in rows:
            if output.company_id in seen:
                continue
            seen.add(output.company_id)
            try:
                daily = json.loads(output.output_json)["data"]["daily"]
            except (KeyError, ValueError, TypeError):
                continue
            rsi_v = daily.get("rsi_14")
            trigger = None
            if rsi_v is not None and rsi_v >= 70:
                trigger = ("rsi_overbought", f"{symbol} RSI(14) {rsi_v:.0f} >= 70 (overbought zone)", rsi_v, 70.0)
            elif rsi_v is not None and rsi_v <= 30:
                trigger = ("rsi_oversold", f"{symbol} RSI(14) {rsi_v:.0f} <= 30 (oversold zone)", rsi_v, 30.0)
            elif daily.get("breakout"):
                trigger = ("breakout", f"{symbol} confirmed breakout above resistance {daily.get('resistance')}", None, None)
            elif daily.get("breakdown"):
                trigger = ("breakdown", f"{symbol} broke below support {daily.get('support')}", None, None)
            if trigger:
                alert_type, message, value, threshold = trigger
                session.add(Alert(
                    company_id=output.company_id, alert_type=alert_type,
                    message=message, severity="info",
                    triggered_value=value, threshold=threshold,
                ))
                created += 1
    return created


def check_score_changes(threshold_points: float = 10.0) -> int:
    """Compare the two latest score rows per company; alert on big moves."""
    created = 0
    with session_scope() as session:
        company_ids = session.scalars(select(ResearchScore.company_id).distinct()).all()
        for company_id in company_ids:
            rows = session.scalars(
                select(ResearchScore)
                .where(ResearchScore.company_id == company_id)
                .order_by(ResearchScore.created_at.desc())
                .limit(2)
            ).all()
            if len(rows) < 2 or rows[0].balanced_score is None or rows[1].balanced_score is None:
                continue
            delta = rows[0].balanced_score - rows[1].balanced_score
            if abs(delta) >= threshold_points:
                symbol = session.get(Company, company_id).symbol
                session.add(
                    Alert(
                        company_id=company_id,
                        alert_type="score_change",
                        message=f"{symbol} balanced score moved {delta:+.1f} pts "
                                f"({rows[1].balanced_score} -> {rows[0].balanced_score})",
                        severity="info",
                        triggered_value=delta,
                        threshold=threshold_points,
                    )
                )
                created += 1
    return created
