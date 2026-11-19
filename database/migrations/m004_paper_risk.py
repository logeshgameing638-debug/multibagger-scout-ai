"""Add risk gate columns to paper_orders."""
from sqlalchemy import text

TABLES = [
    "ALTER TABLE paper_orders ADD COLUMN risk_status VARCHAR(16) NOT NULL DEFAULT 'approved'",
    "ALTER TABLE paper_orders ADD COLUMN risk_reasons TEXT NOT NULL DEFAULT ''",
]


def upgrade(engine) -> None:
    with engine.begin() as conn:
        for ddl in TABLES:
            try:
                conn.execute(text(ddl))
            except Exception:
                pass  # column already exists (fresh DBs create it via models)
