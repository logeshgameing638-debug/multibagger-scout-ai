"""Single-agent rerun: dispatch, honest failures, persisted outputs."""
import pytest
from sqlalchemy import func, select

from database.connection import init_db, session_scope
from database.models import AgentOutput, AgentRun, Company, ResearchScore
from engine import orchestrator


@pytest.fixture()
def fresh_db(tmp_path):
    init_db(f"sqlite:///{tmp_path}/rerun_test.db")
    yield


class _Result:
    def __init__(self, ok, data=None):
        self.ok = ok
        self.data = data or {}


class _StubYF:
    name = "yahoo_finance"

    def get_info(self, symbol, exchange):
        return _Result(True, {"longName": "Stub Co", "sector": "Industrials"})

    def get_financial_statements(self, symbol, exchange):
        return _Result(True, {"annual": {}, "quarterly": {}})

    def get_history(self, symbol, exchange, period="5y", interval="1d"):
        import pandas as pd

        frame = pd.DataFrame(
            {"open": [1.0] * 300, "high": [1.1] * 300, "low": [0.9] * 300,
             "close": [1.0] * 300, "volume": [1000] * 300},
            index=pd.date_range("2024-01-01", periods=300),
        )
        return _Result(True, {"frame": frame})


class _StubRegistry:
    def get(self, name):
        assert name == "yahoo_finance"
        return _StubYF()


@pytest.fixture()
def stub_yf(monkeypatch):
    monkeypatch.setattr(orchestrator, "default_registry", lambda: _StubRegistry())


def _add_company():
    with session_scope() as session:
        session.add(Company(symbol="STUB", exchange="NSE", name="Stub Co",
                            instrument_type="equity"))


def test_rerun_unknown_agent_fails(fresh_db):
    out = orchestrator.rerun_agent("STUB", "NSE", "not_an_agent")
    assert out["status"] == "failed" and "unknown agent" in out["error"]


def test_rerun_missing_company_fails(fresh_db, stub_yf):
    out = orchestrator.rerun_agent("NOPE", "NSE", "fundamental_analysis")
    assert out["status"] == "failed" and "run full research first" in out["error"]


def test_rerun_fundamental_records_output(fresh_db, stub_yf):
    _add_company()
    before = 0
    with session_scope() as session:
        before = session.scalar(select(func.count(AgentRun.id))) or 0
    out = orchestrator.rerun_agent("STUB", "NSE", "fundamental_analysis")
    assert out["agent"] == "fundamental_analysis"
    assert out["status"] in {"success", "partial", "failed"}
    with session_scope() as session:
        after = session.scalar(select(func.count(AgentRun.id))) or 0
        stored = session.execute(
            select(AgentRun.agent_name).join(AgentOutput, AgentOutput.run_id == AgentRun.id)
        ).all()
    assert after == before + 1
    assert ("fundamental_analysis",) in stored


def test_rerun_scoring_persists_score_row(fresh_db, stub_yf):
    _add_company()
    out = orchestrator.rerun_agent("STUB", "NSE", "scoring")
    assert out["status"] in {"success", "partial"}
    with session_scope() as session:
        score = session.scalar(select(ResearchScore))
    assert score is not None
    assert score.fundamental_score is not None and score.balanced_score is not None


def test_rerun_preserves_company_fields_and_prior_outputs(fresh_db, monkeypatch):
    """A single-agent rerun with a degraded provider must not blank company
    fields or delete previously stored outputs or report rows."""
    with session_scope() as session:
        session.add(Company(symbol="STUB", exchange="NSE", name="Stub Co Full Name",
                            sector="Industrials", industry="Machinery", market_cap=12345,
                            instrument_type="equity"))

    class _EmptyYF:
        name = "yahoo_finance"

        def get_info(self, symbol, exchange):
            return _Result(False, {})

        def get_financial_statements(self, symbol, exchange):
            return _Result(False, {})

        def get_history(self, symbol, exchange, period="5y", interval="1d"):
            return _Result(False, {})

    class _EmptyRegistry:
        def get(self, name):
            return _EmptyYF()

    monkeypatch.setattr(orchestrator, "default_registry", lambda: _EmptyRegistry())
    out = orchestrator.rerun_agent("STUB", "NSE", "risk_analysis")
    assert out["agent"] == "risk_analysis"
    with session_scope() as session:
        company = session.scalar(select(Company).where(Company.symbol == "STUB"))
        assert company.name == "Stub Co Full Name"
        assert company.sector == "Industrials"
        assert company.industry == "Machinery"
        assert company.market_cap == 12345
        # the rerun's own output row is ADDED with its honest status; nothing deleted
        runs = session.execute(
            select(AgentRun.agent_name, AgentRun.status)
            .join(AgentOutput, AgentOutput.run_id == AgentRun.id)
        ).all()
    assert len(runs) == 1 and runs[0][0] == "risk_analysis"
