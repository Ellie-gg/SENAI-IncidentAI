from __future__ import annotations

import httpx
import pytest
import respx

from app.config import get_settings
from app.services.notifier import notify_incident, should_notify

WEBHOOK_URL = "http://n8n.test/webhook/incidentai-alert"


@pytest.fixture(autouse=True)
def _reset_settings():
    yield
    get_settings.cache_clear()


def test_should_notify_respects_default_threshold_high(monkeypatch):
    monkeypatch.setenv("NOTIFY_MIN_SEVERITY", "high")
    get_settings.cache_clear()
    assert should_notify("critical") is True
    assert should_notify("high") is True
    assert should_notify("medium") is False
    assert should_notify("low") is False


def test_should_notify_respects_lower_threshold(monkeypatch):
    monkeypatch.setenv("NOTIFY_MIN_SEVERITY", "medium")
    get_settings.cache_clear()
    assert should_notify("medium") is True
    assert should_notify("low") is False


async def test_notify_incident_skips_when_webhook_not_configured(monkeypatch):
    monkeypatch.setenv("N8N_WEBHOOK_URL", "")
    get_settings.cache_clear()
    sent = await notify_incident(
        incident_id="INC-1",
        trace_id="t1",
        service="payments-api",
        environment="production",
        severity="critical",
        category="database_connectivity",
        probable_cause="x",
        requires_human_approval=False,
    )
    assert sent is False


async def test_notify_incident_skips_when_below_threshold(monkeypatch):
    monkeypatch.setenv("N8N_WEBHOOK_URL", WEBHOOK_URL)
    monkeypatch.setenv("NOTIFY_MIN_SEVERITY", "high")
    get_settings.cache_clear()
    sent = await notify_incident(
        incident_id="INC-2",
        trace_id="t2",
        service="payments-api",
        environment="production",
        severity="low",
        category="unknown",
        probable_cause="x",
        requires_human_approval=False,
    )
    assert sent is False


@respx.mock
async def test_notify_incident_posts_payload_when_above_threshold(monkeypatch):
    monkeypatch.setenv("N8N_WEBHOOK_URL", WEBHOOK_URL)
    monkeypatch.setenv("NOTIFY_MIN_SEVERITY", "high")
    get_settings.cache_clear()

    route = respx.post(WEBHOOK_URL).mock(return_value=httpx.Response(200, json={"ok": True}))

    sent = await notify_incident(
        incident_id="INC-3",
        trace_id="t3",
        service="payments-api",
        environment="production",
        severity="critical",
        category="database_connectivity",
        probable_cause="Connection pool exhaustion",
        requires_human_approval=True,
    )

    assert sent is True
    assert route.call_count == 1
    body = route.calls[0].request.content
    import json

    payload = json.loads(body)
    assert payload["incident_id"] == "INC-3"
    assert payload["severity"] == "critical"
    assert payload["requires_human_approval"] is True


@respx.mock
async def test_notify_incident_never_raises_on_webhook_failure(monkeypatch):
    monkeypatch.setenv("N8N_WEBHOOK_URL", WEBHOOK_URL)
    monkeypatch.setenv("NOTIFY_MIN_SEVERITY", "high")
    get_settings.cache_clear()

    respx.post(WEBHOOK_URL).mock(side_effect=httpx.ConnectError("connection refused"))

    # não deve lançar — notificação é best-effort
    sent = await notify_incident(
        incident_id="INC-4",
        trace_id="t4",
        service="payments-api",
        environment="production",
        severity="critical",
        category="unknown",
        probable_cause="x",
        requires_human_approval=False,
    )
    assert sent is True  # tentativa foi feita, mesmo tendo falhado
