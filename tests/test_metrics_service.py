"""Testes do MetricsService."""
from unittest.mock import MagicMock

import pytest

from app.metrics_service import MetricsService


@pytest.fixture
def mock_jira():
    """Cliente Jira mockado."""
    client = MagicMock()
    client.search_total.return_value = 15
    client.is_configured = True
    return client


@pytest.fixture
def metrics_config():
    """Configuração de métricas para teste."""
    return {
        "backlog_total": {
            "name": "Backlog Total",
            "jql": "project = IS AND statusCategory != Done",
        },
        "waiting_for_support": {
            "name": "Waiting for Support",
            "jql": "status = 'Waiting for support'",
        },
    }


def test_refresh_metric(mock_jira, metrics_config):
    """refresh_metric busca valor no Jira e armazena."""
    service = MetricsService(mock_jira, metrics_config)
    result = service.refresh_metric("backlog_total")

    assert result is not None
    assert result["key"] == "backlog_total"
    assert result["name"] == "Backlog Total"
    assert result["value"] == 15
    mock_jira.search_total.assert_called_once()


def test_refresh_metric_unknown_key(mock_jira, metrics_config):
    """refresh_metric retorna None para chave inexistente."""
    service = MetricsService(mock_jira, metrics_config)
    result = service.refresh_metric("nao_existe")
    assert result is None


def test_refresh_metric_missing_jql(mock_jira):
    """refresh_metric levanta erro se JQL não estiver configurado."""
    config = {"bad_metric": {"name": "Bad"}}  # sem jql
    service = MetricsService(mock_jira, config)
    with pytest.raises(ValueError, match="sem JQL"):
        service.refresh_metric("bad_metric")


def test_refresh_all(mock_jira, metrics_config):
    """refresh_all atualiza todas as métricas configuradas."""
    service = MetricsService(mock_jira, metrics_config)
    service.refresh_all()

    all_metrics = service.get_all()
    assert len(all_metrics) == 2
    assert "backlog_total" in all_metrics
    assert "waiting_for_support" in all_metrics
    assert mock_jira.search_total.call_count == 2


def test_get_one(mock_jira, metrics_config):
    """get_one retorna métrica específica ou None."""
    service = MetricsService(mock_jira, metrics_config)
    service.refresh_metric("backlog_total")

    metric = service.get_one("backlog_total")
    assert metric is not None
    assert metric["value"] == 15

    assert service.get_one("nao_existe") is None


def test_last_updated_iso(mock_jira, metrics_config):
    """last_updated_iso retorna None antes do refresh."""
    service = MetricsService(mock_jira, metrics_config)
    assert service.last_updated_iso is None

    service.refresh_all()
    assert service.last_updated_iso is not None
    assert "T" in service.last_updated_iso  # formato ISO
