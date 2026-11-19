"""Connector base contract.

Every provider adapter returns ConnectorResult, records its own health in the
data_sources table, and never invents data: failures come back as errors.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from database.connection import session_scope
from database.models import DataSource


class ConnectorError(Exception):
    pass


@dataclass
class ConnectorResult:
    ok: bool
    source: str
    data: Any = None
    error: str | None = None
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    from_cache: bool = False
    delayed: bool = False  # True when the provider's data is known to be delayed


class BaseConnector:
    name = "base"
    type = "generic"
    base_url = ""

    def record_health(self, ok: bool, error: str | None = None) -> None:
        try:
            with session_scope() as session:
                source = session.scalar(select(DataSource).where(DataSource.name == self.name))
                if source is None:
                    source = DataSource(name=self.name, type=self.type, base_url=self.base_url)
                    session.add(source)
                now = datetime.now(timezone.utc)
                source.last_checked_at = now
                if ok:
                    source.status = "ok"
                    source.last_success_at = now
                    source.last_error = None
                else:
                    source.status = "down" if (source.last_success_at is None) else "degraded"
                    source.last_error = (error or "")[:2000]
        except Exception:
            # Health recording must never break a scan.
            pass

    def _request_with_retry(self, request_fn, attempts: int = 3, backoff_seconds: float = 1.5):
        """Retry transient failures with backoff. Rate-limit (429) waits longer."""
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                return request_fn()
            except Exception as exc:  # provider-specific mapping happens in callers
                last_error = exc
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if status == 429:
                    time.sleep(backoff_seconds * (attempt + 2) * 2)
                else:
                    time.sleep(backoff_seconds * (attempt + 1))
        raise ConnectorError(str(last_error))
