"""Testes E2E: a pilha inteira (API -> grafo -> tools -> monitoramento ->
RAG -> risco -> segurança -> observabilidade) exercitada junto, como o
enunciado pede (item 4.7: "pelo menos um dos seguintes tipos: integração,
aceitação ou E2E").

O serviço mock-monitoring roda IN-PROCESS via `httpx.ASGITransport` (sem
subir container) — mesma app FastAPI (`mock_monitoring/main.py`) que o
`docker-compose.yml` usa, só o transporte de rede muda. Isso deixa o teste
determinístico e rápido, mantendo cobertura real do caminho HTTP completo
do cliente de monitoramento (timeout/retry/fallback continuam cobertos
separadamente em tests/unit/test_monitoring_client.py com respx).

Ver docs/qa/priorizacao-testes.md para a justificativa de por que estes
dois cenários (não outros) foram escolhidos como os E2E prioritários.
"""

from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport

from app.config import get_settings
from app.memory import db as memory_db
from app.memory.incident_repository import save_incident
from app.memory.ingest_runbooks import ingest_runbooks
from app.tools import core as tools_core
from mock_monitoring.main import app as mock_monitoring_app
from scripts.seed_incidents import INCIDENTS


@pytest.fixture
async def real_monitoring(monkeypatch):
    """Aponta app/tools/core.py para o mock-monitoring real, mas
    in-process (ASGITransport) — sem isso, MONITORING_ENABLED=false
    (default dos testes) faz o cliente devolver status=unknown sem nem
    tentar a chamada."""
    monkeypatch.setenv("MONITORING_ENABLED", "true")
    get_settings.cache_clear()

    transport = ASGITransport(app=mock_monitoring_app)
    client = httpx.AsyncClient(transport=transport, base_url="http://mock-monitoring")
    tools_core._client = client
    yield
    await client.aclose()
    tools_core._client = None
    monkeypatch.setenv("MONITORING_ENABLED", "false")
    get_settings.cache_clear()


@pytest.fixture
def seeded_memory():
    """Popula o banco singleton (app/memory/db.get_connection()) com os
    mesmos incidentes canônicos do seed real + os runbooks reais do
    projeto — para o nó search_incident_history achar evidência de
    verdade, igual à demo."""
    conn = memory_db.get_connection()
    for incident in INCIDENTS:
        save_incident(conn, **incident)
    settings = get_settings()
    ingest_runbooks(conn, settings.runbooks_dir)
    return conn


# --------------------------------------------------------------------------
# Cenário 1 (fluxo principal): incidente real de banco de dados, serviço
# degradado com tendência de erro crescente — o caso canônico do
# enunciado. Prioridade alta: é o caminho que exercita TODOS os
# componentes não-triviais do sistema no mesmo teste (LLM, tool HTTP com
# histórico real, RAG com resultado relevante, motor de risco com
# tendência genuína, política de aprovação) — ver justificativa completa
# em docs/qa/priorizacao-testes.md.
# --------------------------------------------------------------------------


async def test_payments_api_high_risk_scenario_full_stack(
    app_client, real_monitoring, seeded_memory
):
    payload = {
        "service": "payments-api",
        "environment": "production",
        "description": "API presenting database connection errors",
        "logs": [
            "ERROR database connection timeout",
            "ERROR connection pool exhausted",
            "WARN latency=2350ms",
        ],
    }
    r = app_client.post("/incidents/analyze", json=payload)
    assert r.status_code == 200
    body = r.json()

    # tool HTTP real (in-process): histórico genuíno do payments-api
    assert body["evidence"]["service_status"] == "degraded"
    assert body["evidence"]["monitoring_source"] == "monitoring"

    # motor de risco real: tendência calculada a partir do histórico real
    assert body["risk"]["trend"] == "increasing"
    assert body["severity"] in ("high", "critical")

    # RAG real: recupera os incidentes/runbooks certos
    assert "INC-00001" in body["evidence"]["similar_incidents"]
    assert any("Connection Pool" in r for r in body["evidence"]["runbooks"])

    # categoria correta, vinda do LLM (mock determinístico por keyword)
    assert body["category"] == "database_connectivity"
    assert len(body["recommended_actions"]) >= 1

    # observabilidade: auditoria e trilha reconstruíveis pelo mesmo trace_id
    audit = app_client.get(f"/incidents/{body['incident_id']}/audit").json()
    assert audit["incident_id"] == body["incident_id"]


# --------------------------------------------------------------------------
# Cenário 2 (risco/falha/anômalo): monitoramento indisponível (timeout
# real, retry esgotado) + descrição sem sinais claros -> o sistema precisa
# degradar graciosamente em TRÊS camadas ao mesmo tempo (tool, LLM
# confidence baixa, ausência de dado) sem nunca quebrar. Prioridade alta:
# é o cenário que prova resiliência de ponta a ponta, não só o caminho
# feliz — ver docs/qa/priorizacao-testes.md.
# --------------------------------------------------------------------------


async def test_monitoring_down_degrades_gracefully_full_stack(
    app_client, real_monitoring, seeded_memory
):
    # força o mock-monitoring a "cair" (500) para os próximos requests
    async with httpx.AsyncClient(
        transport=ASGITransport(app=mock_monitoring_app), base_url="http://mock-monitoring"
    ) as control_client:
        await control_client.post("/_control/fail", params={"mode": "500"})

    payload = {
        "service": "legacy-batch",
        "environment": "production",
        "description": "Something unusual is happening, cause is unclear",
        "logs": [],
    }
    r = app_client.post("/incidents/analyze", json=payload)

    assert r.status_code == 200  # nunca 500 pro cliente, mesmo com tudo indisponível
    body = r.json()
    assert body["evidence"]["service_status"] == "unknown"
    assert body["evidence"]["monitoring_source"] == "fallback"
    assert body["security_violation"] is False
    # monitoramento indisponível não pode ter fabricado um risco alto sozinho
    # (ver app/risk/anomaly.py — peso brando pra status=unknown)
    assert body["risk"]["failure_risk"] < 0.5

    # reset pro resto da suíte
    async with httpx.AsyncClient(
        transport=ASGITransport(app=mock_monitoring_app), base_url="http://mock-monitoring"
    ) as control_client:
        await control_client.post("/_control/reset")
