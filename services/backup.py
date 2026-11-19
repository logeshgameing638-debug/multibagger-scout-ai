"""Database backup and restore (SQLite file copy with timestamp)."""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path


def _sqlite_path(database_url: str) -> Path | None:
    if not database_url.startswith("sqlite:///"):
        return None
    return Path(database_url.replace("sqlite:///", "", 1))


def backup_database(database_url: str, backups_dir: Path | None = None) -> Path:
    source = _sqlite_path(database_url)
    if source is None:
        raise ValueError("backup via file copy supports SQLite only; use pg_dump for PostgreSQL")
    if not source.exists():
        raise FileNotFoundError(f"database not found: {source}")
    target_dir = backups_dir or (source.parent / "backups")
    target_dir.mkdir(exist_ok=True)
    target = target_dir / f"multibagger_backup_{datetime.now():%Y%m%d_%H%M%S}.db"
    shutil.copy2(source, target)
    return target


def restore_database(backup_path: Path, database_url: str) -> Path:
    source = _sqlite_path(database_url)
    if source is None:
        raise ValueError("restore via file copy supports SQLite only")
    if not backup_path.exists():
        raise FileNotFoundError(f"backup not found: {backup_path}")
    shutil.copy2(backup_path, source)
    return source
