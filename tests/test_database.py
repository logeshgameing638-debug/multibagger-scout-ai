"""Database storage: migrations, constraints, persistence."""
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from database.connection import get_engine, init_db, session_scope
from database.models import Company, MarketPrice, SchemaMigration


@pytest.fixture(scope="module", autouse=True)
def _init():
    init_db()


def test_migrations_recorded():
    engine = get_engine()
    with session_scope() as session:
        versions = session.scalars(select(SchemaMigration.version)).all()
    assert 1 in versions


def test_company_insert_and_unique_constraint():
    with session_scope() as session:
        session.add(Company(symbol="TESTCO", exchange="NSE", name="Test Co"))
    with pytest.raises(IntegrityError):
        with session_scope() as session:
            session.add(Company(symbol="TESTCO", exchange="NSE", name="Duplicate"))
            session.flush()


def test_same_symbol_allowed_on_other_exchange():
    with session_scope() as session:
        session.add(Company(symbol="TESTCO", exchange="BSE", name="Test Co BSE"))
    with session_scope() as session:
        count = session.scalars(select(Company).where(Company.symbol == "TESTCO")).all()
    assert len(count) == 2


def test_price_point_dedupe():
    from datetime import datetime

    with session_scope() as session:
        company = session.scalar(select(Company).where(Company.symbol == "TESTCO", Company.exchange == "NSE"))
        session.add(MarketPrice(company_id=company.id, ts=datetime(2024, 1, 2), interval="1d",
                                open=1, high=2, low=0.5, close=1.5, volume=100, source="test"))
    with pytest.raises(IntegrityError):
        with session_scope() as session:
            company = session.scalar(select(Company).where(Company.symbol == "TESTCO", Company.exchange == "NSE"))
            session.add(MarketPrice(company_id=company.id, ts=datetime(2024, 1, 2), interval="1d",
                                    open=1, high=2, low=0.5, close=1.5, volume=100, source="test"))
            session.flush()


def test_financial_statements_preserve_history():
    from datetime import datetime

    from database.models import FinancialStatement

    with session_scope() as session:
        company = session.scalar(select(Company).where(Company.symbol == "TESTCO", Company.exchange == "NSE"))
        for year in (2022, 2023):
            session.add(FinancialStatement(
                company_id=company.id, period_type="annual",
                period_end=datetime(year, 3, 31), statement_type="income",
                metric="Total Revenue", value=100.0 * year, source="test",
            ))
    with session_scope() as session:
        rows = session.scalars(select(FinancialStatement)).all()
    assert len(rows) == 2  # both periods preserved, never overwritten
