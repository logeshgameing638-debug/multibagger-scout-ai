"""Floor 00: central command center status for the trading building.

Every number comes from the live database - agent runs, universe queue, data
source health, alerts, paper orders. A floor shows ACTIVITY only when a real
run happened recently; nothing is animated for decoration.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from database.connection import session_scope
from database.models import (
    AgentOutput,
    AgentRun,
    Alert,
    Company,
    DataSource,
    Decision,
    PaperOrder,
)

# Which agents belong to which floor, for per-floor status and logs.
FLOOR_AGENTS = {
    1: ["stock_scout"],
    2: ["fundamental_analysis", "technical_analysis", "business_quality", "valuation"],
    3: ["risk_analysis"],
    5: ["news_intelligence"],
    7: ["scoring"],
}

RECENT_MINUTES = 10


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def floor_activity() -> dict[int, dict]:
    """Per-floor activity: RUNNING (an agent run is open right now) is kept
    strictly separate from RECENT (last finished run or paper event).

    Only `running` may drive pulsing animation; recent activity is text.
    """
    now = _utcnow()
    recent_cutoff = now - timedelta(minutes=RECENT_MINUTES)
    stale_cutoff = now - timedelta(minutes=30)
    with session_scope() as session:
        rows = session.execute(
            select(AgentRun.agent_name, func.max(AgentRun.finished_at), func.count())
            .group_by(AgentRun.agent_name)
        ).all()
        running_agents = set(session.scalars(
            select(AgentRun.agent_name).where(
                AgentRun.finished_at.is_(None),
                AgentRun.started_at >= stale_cutoff)
        ).all())
        recent_agents = set(session.scalars(
            select(AgentRun.agent_name).where(
                AgentRun.finished_at.is_not(None),
                AgentRun.finished_at >= recent_cutoff)
        ).all())
    by_agent = {name: {"last": str(last)[:16] if last else None, "runs": count}
                for name, last, count in rows}
    floors: dict[int, dict] = {}
    for floor, agents in FLOOR_AGENTS.items():
        stats = [by_agent.get(a, {}) for a in agents]
        last = max((s.get("last") or "" for s in stats), default="") or None
        floors[floor] = {
            "last_run": last,
            "total_runs": sum(s.get("runs", 0) for s in stats),
            "running": any(a in running_agents for a in agents),
            "recent": any(a in recent_agents for a in agents),
        }
    for floor in (0, 4, 6):
        floors[floor] = {"last_run": None, "total_runs": 0,
                         "running": False, "recent": False}
    with session_scope() as session:
        recent_paper = session.scalar(
            select(func.count(PaperOrder.id)).where(PaperOrder.created_at >= recent_cutoff)
        ) or 0
        floors[4]["total_runs"] = session.scalar(select(func.count(PaperOrder.id))) or 0
        last_order = session.scalar(select(func.max(PaperOrder.created_at)))
        floors[4]["last_run"] = str(last_order)[:16] if last_order else None
        # paper orders are instant events: recent, never "running"
        floors[4]["recent"] = recent_paper > 0
        floors[6]["recent"] = recent_paper > 0
        floors[6]["last_run"] = floors[4]["last_run"]
        floors[6]["total_runs"] = floors[4]["total_runs"]
    return floors


def command_status() -> dict:
    """Ground-floor dashboard: queue, agents, database, sources, alerts."""
    with session_scope() as session:
        total_companies = session.scalar(
            select(func.count(Company.id)).where(Company.is_active.is_(True))) or 0
        by_status = dict(session.execute(
            select(Company.research_status, func.count()).group_by(Company.research_status)
        ).all())
        runs_24h = session.scalar(
            select(func.count(AgentRun.id)).where(
                AgentRun.started_at >= _utcnow() - timedelta(hours=24))) or 0
        failed_24h = session.scalar(
            select(func.count(AgentRun.id)).where(
                AgentRun.started_at >= _utcnow() - timedelta(hours=24),
                AgentRun.status == "failed")) or 0
        open_alerts = session.scalar(
            select(func.count(Alert.id)).where(Alert.status == "open")) or 0
        paper_orders = session.scalar(select(func.count(PaperOrder.id))) or 0
        decisions = session.scalar(select(func.count(Decision.id))) or 0
        sources = [{"name": s.name, "status": s.status,
                    "last_success": str(s.last_success_at)[:16] if s.last_success_at else None,
                    "last_error": (s.last_error or "")[:120]}
                   for s in session.scalars(select(DataSource)).all()]
    db_ok = True
    try:
        with session_scope() as session:
            session.execute(select(1))
    except Exception:
        db_ok = False
    return {
        "companies": total_companies,
        "queue": by_status,
        "runs_24h": runs_24h,
        "failed_24h": failed_24h,
        "open_alerts": open_alerts,
        "paper_orders": paper_orders,
        "decisions": decisions,
        "sources": sources,
        "database_ok": db_ok,
        "generated_at": str(_utcnow())[:19],
    }


def activity_log(limit: int = 25, agents: list[str] | None = None) -> list[dict]:
    """Global activity feed: agent runs + alerts + paper orders, newest first."""
    events: list[dict] = []
    with session_scope() as session:
        query = select(AgentRun).order_by(AgentRun.started_at.desc()).limit(limit)
        if agents:
            query = select(AgentRun).where(AgentRun.agent_name.in_(agents)) \
                .order_by(AgentRun.started_at.desc()).limit(limit)
        for run in session.scalars(query).all():
            events.append({
                "ts": str(run.started_at)[:16],
                "kind": "agent",
                "what": f"{run.agent_name}: {run.status}"
                        + (f" - {run.error[:80]}" if run.error else ""),
                "ok": run.status != "failed",
            })
        for alert in session.scalars(
                select(Alert).order_by(Alert.created_at.desc()).limit(10)).all():
            events.append({
                "ts": str(alert.created_at)[:16], "kind": "alert",
                "what": f"{alert.alert_type}: {alert.message[:100]}",
                "ok": alert.severity not in {"high", "critical"},
            })
        for order in session.scalars(
                select(PaperOrder).order_by(PaperOrder.created_at.desc()).limit(10)).all():
            events.append({
                "ts": str(order.created_at)[:16], "kind": "paper",
                "what": f"SIMULATED {order.side} {order.qty} {order.symbol} "
                        f"@ {order.fill_price} ({order.status})",
                "ok": True,
            })
    events.sort(key=lambda e: e["ts"], reverse=True)
    return events[:limit]


def floor_log(floor: int, limit: int = 15) -> list[dict]:
    agents = FLOOR_AGENTS.get(floor)
    if agents is None:  # floors 0/4/6 use the global log slice
        return activity_log(limit)
    return activity_log(limit, agents)
