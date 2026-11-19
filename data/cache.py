"""Simple TTL cache backed by a SQLite table in the project database.

Used to avoid hammering free providers: historical results are cached, and
freshness is explicit through the stored timestamp.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from database.connection import get_engine

DDL = """
CREATE TABLE IF NOT EXISTS provider_cache (
    cache_key TEXT PRIMARY KEY,
    payload TEXT NOT NULL,
    stored_at TEXT NOT NULL
)
"""


def _ensure_table() -> None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text(DDL))


def cache_get(key: str, ttl_minutes: int):
    """Return (payload, stored_at) when present and fresh, else None."""
    _ensure_table()
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT payload, stored_at FROM provider_cache WHERE cache_key = :k"),
            {"k": key},
        ).first()
    if row is None:
        return None
    stored_at = datetime.fromisoformat(row[1])
    if datetime.now(timezone.utc) - stored_at > timedelta(minutes=ttl_minutes):
        return None
    return json.loads(row[0]), stored_at


def cache_get_stale(key: str):
    """Return cached payload regardless of TTL (fallback when provider is down)."""
    _ensure_table()
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT payload, stored_at FROM provider_cache WHERE cache_key = :k"),
            {"k": key},
        ).first()
    if row is None:
        return None
    return json.loads(row[0]), datetime.fromisoformat(row[1])


def cache_set(key: str, payload) -> None:
    _ensure_table()
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO provider_cache (cache_key, payload, stored_at) VALUES (:k, :p, :t) "
                "ON CONFLICT(cache_key) DO UPDATE SET payload = :p, stored_at = :t"
            ),
            {"k": key, "p": json.dumps(payload, default=str), "t": datetime.now(timezone.utc).isoformat()},
        )
