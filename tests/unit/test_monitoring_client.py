"""Testes de resiliência do cliente HTTP de monitoramento: sucesso,
timeout→retry→sucesso, retries esgotados→fallback, 4xx sem retry,
contrato quebrado sem retry. respx mocka o transporte — nenhuma chamada de
rede real acontece.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from app.config import get_settings
from app.tools.monitoring_client import get_service_status

BASE_URL = "http://mock-monitoring.test"


@pytest.fixture(autouse=True)
def _enable_monitoring(monkeypatch):
    monkeypatch.setenv("MONITORING_ENABLED", "true")
    monkeypatch.setenv("MONITORING_BASE_URL", BASE_URL)
    monkeypatch.setenv("MONITORING_MAX_RETRIES", "2")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _payload(**overrides) -> dict:
    payload = {
        "service": "payments-api",
        "status": "degraded",
        "error_rate": 0.14,
        "latency_p95_ms": 1600.0,
        "history": [],
        "source": "monitoring",
    }
    payload.update(overrides)
    return payload


@respx.mock
async def test_success_returns_parsed_status():
    respx.get(f"{BASE_URL}/services/payments-api/status").mock(
        return_value=httpx.Response(200, json=_payload())
    )
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        result = await get_service_status(client, service="payments-api")
    assert result.status == "degraded"
    assert result.source == "monitoring"


@respx.mock
async def test_two_timeouts_then_success_retries_correctly():
    route = respx.get(f"{BASE_URL}/services/auth-api/status")
    route.side_effect = [
        httpx.TimeoutException("timeout 1"),
        httpx.TimeoutException("timeout 2"),
        httpx.Response(200, json=_payload(service="auth-api", status="up", error_rate=0.01)),
    ]
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        result = await get_service_status(client, service="auth-api")
    assert result.status == "up"
    assert route.call_count == 3


@respx.mock
async def test_exhausted_retries_falls_back_to_unknown():
    respx.get(f"{BASE_URL}/services/legacy-batch/status").mock(
        side_effect=httpx.TimeoutException("always times out")
    )
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        result = await get_service_status(client, service="legacy-batch")
    assert result.status == "unknown"
    assert result.source == "fallback"


@respx.mock
async def test_4xx_is_not_retried():
    route = respx.get(f"{BASE_URL}/services/missing-service/status").mock(
        return_value=httpx.Response(404, json={"detail": "not found"})
    )
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        result = await get_service_status(client, service="missing-service")
    assert result.status == "unknown"
    assert route.call_count == 1  # sem retry — 4xx não é transitório


@respx.mock
async def test_malformed_payload_is_not_retried():
    route = respx.get(f"{BASE_URL}/services/broken/status").mock(
        return_value=httpx.Response(200, json={"not": "a valid ServiceStatus"})
    )
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        result = await get_service_status(client, service="broken")
    assert result.status == "unknown"
    assert route.call_count == 1  # contrato quebrado — retry não ajudaria


async def test_monitoring_disabled_short_circuits_without_network(monkeypatch):
    monkeypatch.setenv("MONITORING_ENABLED", "false")
    get_settings.cache_clear()
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        result = await get_service_status(client, service="anything")
    assert result.status == "unknown"
    assert result.source == "fallback"
