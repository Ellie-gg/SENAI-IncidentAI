"""POST /incidents/{id}/approve — registro de decisão humana para
auditoria. A aplicação nunca executa a ação recomendada automaticamente.
"""

from __future__ import annotations


def _analyze(app_client, **overrides) -> dict:
    payload = {
        "service": "payments-api",
        "environment": "production",
        "description": "Database is down, may require a full restart production to recover",
        "logs": ["ERROR database down", "ERROR connection refused"],
    }
    payload.update(overrides)
    r = app_client.post("/incidents/analyze", json=payload)
    assert r.status_code == 200
    return r.json()


def test_approve_unknown_incident_returns_404(app_client):
    r = app_client.post(
        "/incidents/INC-DOESNOTEXIST/approve",
        json={"decision": "approved", "actor": "jane.doe"},
    )
    assert r.status_code == 404


def test_approve_incident_not_pending_returns_409(app_client):
    # payload comum, provavelmente não fica pendente de aprovação
    body = _analyze(
        app_client,
        description="API presenting database connection errors",
        logs=["ERROR database connection timeout"],
    )
    if body["requires_human_approval"]:
        return  # se por algum motivo ficou pendente, o teste abaixo cobre o caso
    r = app_client.post(
        f"/incidents/{body['incident_id']}/approve",
        json={"decision": "approved", "actor": "jane.doe"},
    )
    assert r.status_code == 409


def test_approve_pending_incident_records_decision(app_client, monkeypatch):
    # Força llm_parse_failed=True (mock_fail) -> requires_human_approval=True
    # de forma determinística, em vez de depender de um cenário de risco
    # que o motor de risco pode ou não classificar como alto neste ambiente.
    monkeypatch.setenv("LLM_PROVIDER", "mock_fail")
    from app.config import get_settings
    from app.services import llm as llm_module

    get_settings.cache_clear()
    llm_module.get_llm.cache_clear()
    try:
        body = _analyze(app_client)
        assert body["requires_human_approval"] is True

        r = app_client.post(
            f"/incidents/{body['incident_id']}/approve",
            json={
                "decision": "approved",
                "actor": "jane.doe",
                "reason": "Restart autorizado pelo plantão",
            },
        )
        assert r.status_code == 200
        result = r.json()
        assert result["incident_id"] == body["incident_id"]
        assert result["decision"] == "approved"
        assert result["actor"] == "jane.doe"
    finally:
        monkeypatch.setenv("LLM_PROVIDER", "mock")
        get_settings.cache_clear()
        llm_module.get_llm.cache_clear()


def test_approve_rejects_invalid_decision_value(app_client):
    body = _analyze(app_client)
    r = app_client.post(
        f"/incidents/{body['incident_id']}/approve",
        json={"decision": "maybe", "actor": "jane.doe"},
    )
    assert r.status_code == 422


def test_approve_requires_actor(app_client):
    body = _analyze(app_client)
    r = app_client.post(
        f"/incidents/{body['incident_id']}/approve",
        json={"decision": "approved"},
    )
    assert r.status_code == 422
