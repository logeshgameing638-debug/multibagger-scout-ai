"""Pages 15-17: Alerts, Settings, Data Source Health."""
from __future__ import annotations

import pandas as pd


def render_alerts(st) -> None:
    st.title("Alerts")
    from services import alerts as alerts_service

    if st.button("Check for score changes now"):
        created = alerts_service.check_score_changes()
        st.write(f"{created} new score-change alert(s)")

    status = st.radio("Show", ["open", "acknowledged", "all"], horizontal=True)
    rows = alerts_service.list_alerts(status=None if status == "all" else status)
    if not rows:
        st.info("No alerts.")
        return
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    alert_id = st.number_input("Acknowledge alert id", min_value=0, step=1)
    if st.button("Acknowledge") and alert_id:
        if alerts_service.acknowledge(int(alert_id)):
            st.success("Acknowledged")
        else:
            st.error("Alert not found")


def render_settings(st) -> None:
    st.title("Settings")
    from config import get_settings
    from services import scheduler as scheduler_service

    settings = get_settings()
    st.markdown("**Configuration (from environment / .env)**")
    st.write({
        "database_url": settings.database_url,
        "ollama_enabled": settings.ollama_enabled,
        "scheduler_process_enabled": settings.scheduler_enabled,
        "price_cache_ttl_minutes": settings.price_cache_ttl_minutes,
    })

    st.markdown("**Scheduled jobs** (each can be toggled; they run only while the app process is running)")
    st.caption(
        "Coverage: index scans, watchlist score/risk re-checks (including RSI and breakout "
        "thresholds), and watchlist news refresh. Not monitored yet: exchange announcements, "
        "results calendars and corporate filings - no free source covers them reliably, so they "
        "are not claimed anywhere in the app."
    )
    states = scheduler_service.job_states()
    for job, enabled in states.items():
        new_state = st.toggle(f"{job} - {scheduler_service.JOB_DEFINITIONS[job]['description']}", value=enabled, key=f"job-{job}")
        if new_state != enabled:
            scheduler_service.set_enabled(job, new_state)
            st.toast(f"{job} {'enabled' if new_state else 'disabled'}")

    st.markdown("**Database backup**")
    if st.button("Backup database now"):
        from services.backup import backup_database

        try:
            path = backup_database(settings.database_url)
            st.success(f"Backup written: {path}")
        except Exception as exc:
            st.error(str(exc))


def render_source_health(st) -> None:
    st.title("Data Source Health")
    from data.connectors import default_registry
    from database.connection import session_scope
    from database.models import DataSource
    from sqlalchemy import select

    if st.button("Re-check all sources now"):
        report = default_registry().health_check_all()
        for name, status in report.items():
            (st.success if status["ok"] else st.error)(
                f"{name}: {'ok' if status['ok'] else status['error']}"
            )

    with session_scope() as session:
        rows = session.scalars(select(DataSource)).all()
    if rows:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "source": r.name, "type": r.type, "status": r.status,
                        "last_checked": str(r.last_checked_at),
                        "last_success": str(r.last_success_at),
                        "last_error": (r.last_error or "")[:200],
                    }
                    for r in rows
                ]
            ),
            use_container_width=True, hide_index=True,
        )
    else:
        st.info("No source checks recorded yet.")
    st.caption(
        "If a provider fails, the rest of the app keeps working and the failure stays visible here. "
        "Delayed data is always labelled delayed."
    )
