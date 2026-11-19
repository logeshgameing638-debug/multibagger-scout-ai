"""Minimal ordered migration runner.

Each migration module exposes `upgrade(engine)`. Applied versions are recorded
in the schema_migrations table so migrations never run twice.
"""
from __future__ import annotations

from importlib import import_module

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from database.models import Base, SchemaMigration

MIGRATIONS = ["database.migrations.m001_initial", "database.migrations.m002_universe", "database.migrations.m003_building"]


def applied_versions(engine) -> set[int]:
    if "schema_migrations" not in inspect(engine).get_table_names():
        return set()
    with Session(engine) as session:
        return set(session.scalars(select(SchemaMigration.version)).all())


def run_migrations(engine) -> list[int]:
    applied = applied_versions(engine)
    newly_applied: list[int] = []
    for index, module_path in enumerate(MIGRATIONS, start=1):
        if index in applied:
            continue
        module = import_module(module_path)
        module.upgrade(engine)
        with Session(engine) as session:
            session.add(SchemaMigration(version=index))
            session.commit()
        newly_applied.append(index)
    return newly_applied


__all__ = ["run_migrations", "applied_versions", "Base"]
