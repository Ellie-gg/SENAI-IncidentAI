from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_ok():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_analyze_valid_payload_returns_clear_not_implemented():
    payload = {
        "service": "payments-api",
        "environment": "production",
        "description": "API presenting database connection errors",
        "logs": ["ERROR database connection timeout"],
    }
    r = client.post("/incidents/analyze", json=payload)
    # Fase 2: payload válido passa da validação; grafo ainda não ligado (Fase 3).
    assert r.status_code == 501
    assert "payments-api" in r.json()["detail"]


def test_analyze_missing_required_field_returns_422_with_clear_message():
    payload = {"environment": "production", "description": "x"}  # falta "service"
    r = client.post("/incidents/analyze", json=payload)
    assert r.status_code == 422
    body = r.json()
    assert any(err["loc"][-1] == "service" for err in body["detail"])


def test_analyze_invalid_environment_returns_422():
    payload = {
        "service": "payments-api",
        "environment": "not-a-real-environment",
        "description": "x",
        "logs": [],
    }
    r = client.post("/incidents/analyze", json=payload)
    assert r.status_code == 422


def test_analyze_empty_description_returns_422():
    payload = {
        "service": "payments-api",
        "environment": "production",
        "description": "   ",
        "logs": [],
    }
    r = client.post("/incidents/analyze", json=payload)
    assert r.status_code == 422
