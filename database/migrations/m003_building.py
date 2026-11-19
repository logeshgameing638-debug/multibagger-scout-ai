"""Add paper_orders and decisions tables for the trading-building floors."""
from sqlalchemy import text


TABLES = [
    """CREATE TABLE IF NOT EXISTS paper_orders (
        id INTEGER PRIMARY KEY,
        symbol VARCHAR(32) NOT NULL,
        exchange VARCHAR(8) DEFAULT 'NSE',
        side VARCHAR(8) NOT NULL,
        qty INTEGER NOT NULL,
        order_type VARCHAR(16) DEFAULT 'MARKET',
        status VARCHAR(16) DEFAULT 'open',
        fill_price FLOAT,
        stop_loss FLOAT,
        target FLOAT,
        note TEXT DEFAULT '',
        created_at DATETIME,
        filled_at DATETIME
    )""",
    """CREATE TABLE IF NOT EXISTS decisions (
        id INTEGER PRIMARY KEY,
        company_id INTEGER,
        symbol VARCHAR(32) NOT NULL,
        verdict VARCHAR(16) NOT NULL,
        rationale TEXT DEFAULT '',
        balanced_score FLOAT,
        created_at DATETIME
    )""",
]


def upgrade(engine) -> None:
    with engine.begin() as conn:
        for ddl in TABLES:
            conn.execute(text(ddl))
