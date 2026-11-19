"""Engine/session management. DATABASE_URL decides SQLite vs PostgreSQL."""
from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from config import get_settings

_engine = None
_SessionLocal: sessionmaker | None = None


def get_engine(database_url: str | None = None):
    global _engine, _SessionLocal
    url = database_url or get_settings().database_url
    if _engine is None or str(_engine.url) != url:
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        _engine = create_engine(url, connect_args=connect_args, future=True)
        _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
    return _engine


def get_session() -> Session:
    if _SessionLocal is None:
        get_engine()
    return _SessionLocal()


@contextmanager
def session_scope(database_url: str | None = None):
    if database_url is not None:
        get_engine(database_url)
    session = get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db(database_url: str | None = None) -> None:
    """Create schema through the migration runner (idempotent)."""
    from database.migrations.runner import run_migrations

    engine = get_engine(database_url)
    run_migrations(engine)
