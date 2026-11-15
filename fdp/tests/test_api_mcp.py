"""Smoke tests for the unified FDP FastAPI app and MCP layer."""

from __future__ import annotations

import json
import os

import pytest
from fastapi.testclient import TestClient

from fdp.server import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_analysis_health(client: TestClient) -> None:
    response = client.get("/api/v1/analysis/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "fdp-analysis-api"}


def test_data_health_returns_ok(client: TestClient) -> None:
    """The data API health endpoint now reads parquet files and returns 200."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["election_rows"] > 0


def test_analysis_catalog(client: TestClient) -> None:
    response = client.get("/api/v1/analysis/catalog")
    assert response.status_code == 200
    data = response.json()
    assert "plans" in data
    assert "chambers" in data


def test_openapi_docs(client: TestClient) -> None:
    response = client.get("/docs")
    assert response.status_code == 200


def test_mcp_routes_are_mounted(client: TestClient) -> None:
    """The unified app exposes the MCP SSE and message routes."""
    paths = {getattr(route, "path", getattr(route, "name", None)) for route in app.routes}
    assert "/mcp/sse" in paths
    assert "/mcp/messages" in paths


def test_nlq_defaults_name_error_fixed(monkeypatch: pytest.MonkeyPatch) -> None:
    """analyze_question must not raise NameError after the LLM responds."""
    from fdp.analysis import nlq

    class FakeProvider:
        name = "fake"

        def translate(self, system_prompt: str, user_prompt: str) -> str:
            return json.dumps({
                "type": "analysis",
                "parameters": {"chamber": "congress", "plan_id": "congress_enacted_24"},
            })

    monkeypatch.setattr(nlq, "get_provider", lambda: FakeProvider())
    # Ensure we do not accidentally call a real LLM.
    monkeypatch.setenv("AI_PROVIDER", "fake")
    os.environ["AI_PROVIDER"] = "fake"

    result = nlq.analyze_question("What is the minority VAP?")
    # It will fail later because the plan is not present in the repo, but it
    # must not fail with the NameError that existed before the audit fix.
    assert result.get("type") != "error" or "name 'defaults' is not defined" not in result.get("error", "")
