"""API endpoint tests via FastAPI TestClient (no network calls)."""
import pytest
from fastapi.testclient import TestClient

from backend.api import create_app


@pytest.fixture(scope="module")
def client():
    return TestClient(create_app())


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_companies_empty_list(client):
    response = client.get("/companies")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_alerts_list(client):
    response = client.get("/alerts")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_watchlist_flow_requires_research(client):
    response = client.post("/watchlist", json={"symbol": "NOSUCH", "exchange": "NSE"})
    assert response.status_code == 404  # honest: not researched yet


def test_score_history_unknown_company_404(client):
    response = client.get("/scores/NOSUCH")
    assert response.status_code == 404


def test_sources_health_endpoint(client):
    response = client.get("/sources/health")
    assert response.status_code == 200


def test_job_toggle_validation(client):
    response = client.post("/settings/jobs", json={"job": "nonexistent", "enabled": True})
    assert response.status_code == 400
    response = client.post("/settings/jobs", json={"job": "daily_scan", "enabled": True})
    assert response.status_code == 200
    assert response.json()["states"]["daily_scan"] is True
    client.post("/settings/jobs", json={"job": "daily_scan", "enabled": False})
