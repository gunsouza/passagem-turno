"""Fixtures compartilhadas para os testes."""
import os

import pytest


@pytest.fixture(autouse=True)
def mock_env(monkeypatch):
    """Garante variáveis de ambiente para os testes (antes do app carregar)."""
    monkeypatch.setenv("JIRA_BASE_URL", "https://test.atlassian.net")
    monkeypatch.setenv("JIRA_EMAIL", "test@test.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "fake-token-for-tests")


@pytest.fixture
def mock_jira_search(monkeypatch):
    """Mock do Jira para não fazer chamadas reais."""
    def fake_search_total(jql: str) -> int:
        return 42

    # Patch antes de usar o app (is_configured já é True via env vars do mock_env)
    import app.main as main_module
    monkeypatch.setattr(main_module.jira_client, "search_total", fake_search_total)


@pytest.fixture
def client(mock_jira_search):
    """Cliente HTTP para testar a API."""
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


@pytest.fixture
def mock_metrics():
    """Métricas de exemplo para testes."""
    return {
        "backlog_total": {
            "key": "backlog_total",
            "name": "Backlog Total",
            "value": 10,
            "jql": "project = IS",
            "link": None,
        },
        "waiting_for_support": {
            "key": "waiting_for_support",
            "name": "Waiting for Support",
            "value": 3,
            "jql": "status = Waiting",
            "link": None,
        },
    }
