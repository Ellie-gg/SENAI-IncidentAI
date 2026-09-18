"""Testes do serviço mock-monitoring em si — via ASGITransport in-process,
sem subir container nem rede real.
"""

from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport
from pydantic import ValidationError

from app.models.monitoring import ServiceStatus
from mock_monitoring.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
        await c.post("/_control/reset")  # nunca vaza fail_mode entre testes


async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200


async def test_unknown_service_gets_default_up_scenario(client):
    r = await client.get("/services/some-random-service/status")
    assert r.status_code == 200
    status = ServiceStatus.model_validate(r.json())
    assert status.status == "up"


async def test_payments_api_scenario_is_degraded_with_increasing_error_rate(client):
    r = await client.get("/services/payments-api/status")
    status = ServiceStatus.model_validate(r.json())
    assert status.status == "degraded"
    assert status.error_rate == pytest.approx(0.19)
    assert len(status.history) == 5
    # tendência claramente crescente — é o caso canônico do enunciado
    rates = [p.error_rate for p in status.history]
    assert rates == sorted(rates)


async def test_legacy_batch_scenario_is_down(client):
    r = await client.get("/services/legacy-batch/status")
    status = ServiceStatus.model_validate(r.json())
    assert status.status == "down"


async def test_fail_mode_500(client):
    await client.post("/_control/fail", params={"mode": "500"})
    r = await client.get("/services/payments-api/status")
    assert r.status_code == 500


async def test_fail_mode_garbage_returns_200_but_invalid_contract(client):
    await client.post("/_control/fail", params={"mode": "garbage"})
    r = await client.get("/services/payments-api/status")
    assert r.status_code == 200
    with pytest.raises(ValidationError):
        ServiceStatus.model_validate(r.json())


async def test_fail_mode_timeout_sleeps_long_before_responding(client, monkeypatch):
    calls: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        calls.append(seconds)

    monkeypatch.setattr("mock_monitoring.main.asyncio.sleep", fake_sleep)
    await client.post("/_control/fail", params={"mode": "timeout"})
    r = await client.get("/services/payments-api/status")

    assert calls == [10]  # bem acima do timeout de 3s do cliente real
    assert r.status_code == 200  # o servidor eventualmente responde certo


async def test_reset_clears_fail_mode(client):
    await client.post("/_control/fail", params={"mode": "500"})
    await client.post("/_control/reset")
    r = await client.get("/services/payments-api/status")
    assert r.status_code == 200
