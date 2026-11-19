"""Add universe-scan columns to companies (SQLite/Postgres-safe ADD COLUMN)."""
from sqlalchemy import text


COLUMNS = [
    ("isin", "VARCHAR(16)"),
    ("instrument_type", "VARCHAR(24) DEFAULT 'equity'"),
    ("research_status", "VARCHAR(16) DEFAULT 'pending'"),
    ("researched_at", "DATETIME"),
]


def upgrade(engine) -> None:
    with engine.begin() as conn:
        existing = {
            row[1] for row in conn.execute(text("PRAGMA table_info(companies)")).all()
        } if engine.dialect.name == "sqlite" else set()
        for name, ddl in COLUMNS:
            if engine.dialect.name == "sqlite" and name in existing:
                continue
            conn.execute(text(f"ALTER TABLE companies ADD COLUMN {name} {ddl}"))
        if engine.dialect.name == "sqlite":
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_companies_isin ON companies (isin)"))
