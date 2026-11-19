"""Universe loading: ISIN dedupe, non-equity filtering, resumable scanning."""
import pytest
from sqlalchemy import select

from database.connection import init_db, session_scope
from database.models import Company, ExchangeSymbol
from services import universe


@pytest.fixture()
def fresh_db(tmp_path):
    init_db(f"sqlite:///{tmp_path}/universe_test.db")
    yield


class _StubConnector:
    def __init__(self, rows):
        self._rows = rows

    def get_equity_master(self):
        from data.connectors.base import ConnectorResult

        return ConnectorResult(ok=True, source="stub", data=self._rows)


class _StubRegistry:
    def __init__(self, rows):
        self._c = _StubConnector(rows)

    def get(self, name):
        return self._c


def test_load_nse_universe_filters_non_equity_and_dedupes_isin(monkeypatch, fresh_db):
    rows = [
        {"symbol": "AAA", "name": "Alpha", "series": "EQ", "isin": "INE000A00001"},
        {"symbol": "BBB", "name": "Beta", "series": "BE", "isin": "INE000B00002"},   # non-EQ
        {"symbol": "AAA", "name": "Alpha", "series": "EQ", "isin": "INE000A00001"},   # duplicate row
    ]
    monkeypatch.setattr(universe, "default_registry", lambda: _StubRegistry(rows))
    result = universe.load_nse_universe()
    assert result["ok"] and result["added"] == 1 and result["skipped_non_equity"] == 1

    with session_scope() as session:
        alpha = session.scalar(select(Company).where(Company.symbol == "AAA"))
        assert alpha is not None and alpha.isin == "INE000A00001"
        assert alpha.research_status == "pending"
        assert session.scalar(select(Company).where(Company.symbol == "BBB")) is None

    # a BSE company with the same ISIN: an NSE row for it links, no duplicate
    with session_scope() as session:
        session.add(Company(symbol="500001", exchange="BSE", name="Alpha", isin="INE000A00001"))
    rows.append({"symbol": "AAA2", "name": "Alpha NSE", "series": "EQ", "isin": "INE000A00001"})
    result = universe.load_nse_universe()
    assert result["linked_existing"] >= 1
    with session_scope() as session:
        twins = session.scalars(select(Company).where(Company.isin == "INE000A00001")).all()
        assert len(twins) == 2  # AAA (NSE) + 500001 (BSE); AAA2 was linked, not added
        link = session.scalar(
            select(ExchangeSymbol).where(
                ExchangeSymbol.exchange == "NSE", ExchangeSymbol.symbol == "AAA2"
            )
        )
        assert link is not None


def test_scan_universe_resumable_and_statuses(monkeypatch, fresh_db):
    with session_scope() as session:
        for i, symbol in enumerate(["U1", "U2", "U3"]):
            session.add(Company(symbol=symbol, exchange="NSE", name=symbol))

    calls: list[str] = []

    def fake_research(symbol, exchange, generate_report=False):
        calls.append(symbol)
        return {"status": "success" if symbol != "U2" else "partial"}

    import engine.orchestrator as orch
    monkeypatch.setattr(orch, "research_company", fake_research)

    first = universe.scan_universe(batch_size=2, sleep_seconds=0)
    assert first["batch"] == 2 and calls == ["U1", "U2"]
    with session_scope() as session:
        u1 = session.scalar(select(Company).where(Company.symbol == "U1"))
        u2 = session.scalar(select(Company).where(Company.symbol == "U2"))
        assert u1.research_status == "complete" and u2.research_status == "partial"

    second = universe.scan_universe(batch_size=5, sleep_seconds=0)
    assert second["batch"] == 1 and calls[-1] == "U3"  # resumed, no repeats

    progress = universe.universe_progress()
    assert progress["by_status"].get("complete", 0) >= 2


def test_load_bse_universe_dedupes_isin(monkeypatch, fresh_db):
    with session_scope() as session:
        session.add(Company(symbol="AAA", exchange="NSE", name="Alpha",
                            isin="INE000A00001", instrument_type="equity"))
    rows = [
        {"symbol": "ALPHABSE", "name": "Alpha", "isin": "INE000A00001", "exchange": "BSE"},
        {"symbol": "ONLYBSE", "name": "Beta", "isin": "INE000B00002", "exchange": "BSE"},
    ]
    monkeypatch.setattr(universe, "default_registry", lambda: _StubRegistry(rows))
    result = universe.load_bse_universe()
    assert result["ok"] and result["added"] == 1 and result["linked_existing"] == 1
    with session_scope() as session:
        assert session.scalar(select(Company).where(
            Company.symbol == "ALPHABSE", Company.exchange == "BSE")) is None
        link = session.scalar(select(ExchangeSymbol).where(
            ExchangeSymbol.exchange == "BSE", ExchangeSymbol.symbol == "ALPHABSE"))
        assert link is not None
        assert session.scalar(select(Company).where(
            Company.symbol == "ONLYBSE", Company.exchange == "BSE")) is not None
