"""Testes dos endpoints da API."""
import pytest
from fastapi.testclient import TestClient


def test_health(client: TestClient):
    """Health check retorna status ok e métricas."""
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "metrics_count" in data
    assert "last_updated" in data


def test_get_metrics(client: TestClient):
    """GET /metrics retorna todas as métricas."""
    resp = client.get("/metrics")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)
    assert len(data) >= 0  # Pode estar vazio ou com métricas


def test_get_metric_existing(client: TestClient):
    """GET /metrics/{key} retorna métrica existente."""
    # Garante que há métricas (refresh usa o mock do Jira)
    client.post("/refresh", json={})
    metrics_resp = client.get("/metrics")
    assert metrics_resp.status_code == 200
    metrics = metrics_resp.json()
    assert metrics, "Deve haver ao menos uma métrica após o refresh"
    key = next(iter(metrics.keys()))
    resp = client.get(f"/metrics/{key}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["key"] == key
    assert "value" in data
    assert "name" in data


def test_get_metric_not_found(client: TestClient):
    """GET /metrics/{key} retorna 404 para métrica inexistente."""
    resp = client.get("/metrics/nao_existe")
    assert resp.status_code == 404
    assert "não encontrada" in resp.json()["detail"]


def test_refresh_all(client: TestClient):
    """POST /refresh atualiza todas as métricas."""
    resp = client.post("/refresh", json={})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "last_updated" in data


def test_refresh_single(client: TestClient):
    """POST /refresh com key atualiza métrica específica."""
    resp = client.post("/refresh", json={"key": "total"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_refresh_invalid_key(client: TestClient):
    """POST /refresh com key inválida retorna 404."""
    resp = client.post("/refresh", json={"key": "chave_invalida"})
    assert resp.status_code == 404


def test_workflow_report_without_slack(client: TestClient):
    """POST /workflow/report retorna texto sem enviar ao Slack."""
    resp = client.post(
        "/workflow/report",
        json={"title": "Teste", "send_to_slack": False},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "text" in data
    assert "Teste" in data["text"]
    assert data["status"] == "ok"
