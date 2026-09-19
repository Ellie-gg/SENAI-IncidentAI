"""Notificação low-code: dispara um webhook para o n8n quando a
severidade do incidente atinge o limiar configurado (`NOTIFY_MIN_SEVERITY`,
default `high`).

A lógica de QUANDO notificar fica na aplicação (`should_notify` — regra
determinística, testável isoladamente); o QUE FAZER com o alerta
(formatar mensagem, postar no Discord/Slack/e-mail) fica no workflow do
n8n (`n8n/incidentai-alert.json`) — a lógica principal do produto nunca
sai da aplicação, o n8n só orquestra a notificação.

Notificação é best-effort: nunca lança exceção — uma falha no webhook do
n8n não pode derrubar a análise do incidente.
"""

from __future__ import annotations

import httpx

from app.config import get_settings
from app.observability.logger import get_logger

logger = get_logger("incidentai.notifier")

_SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def should_notify(severity: str) -> bool:
    settings = get_settings()
    return _SEVERITY_RANK.get(severity, 0) >= _SEVERITY_RANK.get(settings.notify_min_severity, 2)


async def notify_incident(
    *,
    incident_id: str,
    trace_id: str,
    service: str,
    environment: str,
    severity: str,
    category: str,
    probable_cause: str,
    requires_human_approval: bool,
) -> bool:
    """Retorna True se a notificação foi enviada (ou tentada), False se
    nem era o caso (severidade abaixo do limiar ou webhook não
    configurado)."""
    settings = get_settings()
    if not settings.n8n_webhook_url:
        return False
    if not should_notify(severity):
        return False

    payload = {
        "incident_id": incident_id,
        "trace_id": trace_id,
        "service": service,
        "environment": environment,
        "severity": severity,
        "category": category,
        "probable_cause": probable_cause,
        "requires_human_approval": requires_human_approval,
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(settings.n8n_webhook_url, json=payload)
            response.raise_for_status()
        logger.info("notifier.sent", incident_id=incident_id, severity=severity)
        return True
    except Exception as exc:  # noqa: BLE001 — notificação nunca derruba a análise
        logger.warning("notifier.failed", incident_id=incident_id, error=str(exc))
        return True  # tentativa foi feita — False é reservado para "nem tentou"
