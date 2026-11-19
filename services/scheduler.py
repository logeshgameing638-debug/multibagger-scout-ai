"""Local scheduling via APScheduler (free). Every job can be enabled/disabled
individually; state persists in the settings table. The scheduler runs only
while the dashboard/backend process runs - documented in the README.
"""
from __future__ import annotations

from sqlalchemy import select

from database.connection import session_scope
from database.models import Setting

JOB_DEFINITIONS = {
    "daily_scan": {"description": "Daily scan of the configured index", "default_cron": "mon-fri 18:30"},
    "watchlist_monitor": {"description": "Re-check watchlist names for score/risk changes", "default_cron": "mon-fri 9:30"},
    "news_refresh": {"description": "Refresh news for watchlist companies", "default_cron": "mon-fri * 09-18"},
}

_scheduler = None


def is_enabled(job_name: str) -> bool:
    with session_scope() as session:
        row = session.get(Setting, f"job:{job_name}")
        return row is not None and row.value == "on"


def set_enabled(job_name: str, enabled: bool) -> None:
    if job_name not in JOB_DEFINITIONS:
        raise ValueError(f"unknown job: {job_name}")
    with session_scope() as session:
        row = session.get(Setting, f"job:{job_name}")
        if row is None:
            row = Setting(key=f"job:{job_name}")
            session.add(row)
        row.value = "on" if enabled else "off"


def job_states() -> dict[str, bool]:
    with session_scope() as session:
        rows = session.scalars(select(Setting).where(Setting.key.like("job:%"))).all()
        states = {row.key[4:]: row.value == "on" for row in rows}
    return {name: states.get(name, False) for name in JOB_DEFINITIONS}


def _run_daily_scan() -> None:
    from services.scanner import run_scan

    run_scan(limit=50, generate_reports=False)


def _run_watchlist_monitor() -> None:
    from services.alerts import check_score_changes, check_technical_thresholds
    from services.watchlist import auto_update_from_scores

    auto_update_from_scores()
    check_score_changes()
    check_technical_thresholds()


def _run_news_refresh() -> None:
    from agents.base import run_recorded
    from agents import news_agent
    from services.watchlist import list_items

    for item in list_items():
        run_recorded(
            "news_intelligence",
            lambda item=item: news_agent.analyze(item["name"], item["symbol"]),
            input_summary=f"watchlist refresh {item['symbol']}",
        )


def start_scheduler():
    """Start APScheduler with jobs honoured per their enabled state.

    Returns the scheduler or None when APScheduler is unavailable.
    """
    global _scheduler
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        return None
    if _scheduler is not None:
        return _scheduler

    _scheduler = BackgroundScheduler(timezone="Asia/Kolkata")

    def guarded(job_name: str, fn):
        def wrapper():
            if is_enabled(job_name):
                fn()
        return wrapper

    _scheduler.add_job(guarded("daily_scan", _run_daily_scan), "cron",
                       day_of_week="mon-fri", hour=18, minute=30, id="daily_scan")
    _scheduler.add_job(guarded("watchlist_monitor", _run_watchlist_monitor), "cron",
                       day_of_week="mon-fri", hour=9, minute=30, id="watchlist_monitor")
    _scheduler.add_job(guarded("news_refresh", _run_news_refresh), "cron",
                       day_of_week="mon-fri", hour="9-17", id="news_refresh")
    _scheduler.start()
    return _scheduler
