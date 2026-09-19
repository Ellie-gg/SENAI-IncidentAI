from __future__ import annotations


def test_health_ok(app_client):
    r = app_client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_analyze_valid_payload_runs_graph_end_to_end(app_client):
    payload = {
        "service": "payments-api",
        "environment": "production",
        "description": "API presenting database connection errors",
        "logs": ["ERROR database connection timeout", "ERROR connection pool exhausted"],
    }
    r = app_client.post("/incidents/analyze", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["incident_id"].startswith("INC-")
    assert body["trace_id"]
    assert body["category"] == "database_connectivity"
    assert 0.0 <= body["confidence"] <= 1.0
    assert body["risk"]["trend"] in ("increasing", "stable", "decreasing")
    assert len(body["recommended_actions"]) >= 1
    assert body["terminal_reason"] == "completed"


def test_analyze_missing_required_field_returns_422_with_clear_message(app_client):
    payload = {"environment": "production", "description": "x"}  # falta "service"
    r = app_client.post("/incidents/analyze", json=payload)
    assert r.status_code == 422
    body = r.json()
    assert any(err["loc"][-1] == "service" for err in body["detail"])


def test_analyze_invalid_environment_returns_422(app_client):
    payload = {
        "service": "payments-api",
        "environment": "not-a-real-environment",
        "description": "x",
        "logs": [],
    }
    r = app_client.post("/incidents/analyze", json=payload)
    assert r.status_code == 422


def test_analyze_empty_description_returns_422(app_client):
    payload = {
        "service": "payments-api",
        "environment": "production",
        "description": "   ",
        "logs": [],
    }
    r = app_client.post("/incidents/analyze", json=payload)
    assert r.status_code == 422
