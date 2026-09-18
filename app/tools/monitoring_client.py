"""Cliente HTTP resiliente para o serviço mock-monitoring.

Política: timeout de 3s (configurável), até 2 retries com backoff+jitter
para erros de rede/timeout/5xx. 4xx e falha de validação de schema NÃO são
retentados — nenhum dos dois é transitório, tentar de novo só adiciona
latência. Qualquer esgotamento da política devolve `ServiceStatus` com
`status="unknown", source="fallback"` — o chamador nunca recebe exceção.
"""

from __future__ import annotations

import asyncio
import random

import httpx
import structlog
from pydantic import ValidationError

from app.config import get_settings
from app.models.monitoring import ServiceStatus

logger = structlog.get_logger(__name__)

_RETRYABLE_NETWORK = (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError)
_BACKOFF_SECONDS = (0.1, 0.2)


async def get_service_status(
    client: httpx.AsyncClient, *, service: str, environment: str = "production"
) -> ServiceStatus:
    settings = get_settings()
    if not settings.monitoring_enabled:
        return ServiceStatus(service=service, status="unknown", source="fallback")

    attempts = settings.monitoring_max_retries + 1
    last_error: Exception | None = None

    for attempt in range(attempts):
        try:
            response = await client.get(
                f"/services/{service}/status",
                params={"environment": environment},
                timeout=httpx.Timeout(settings.monitoring_timeout_seconds, connect=1.0),
            )
            response.raise_for_status()
            return ServiceStatus.model_validate(response.json())
        except _RETRYABLE_NETWORK as exc:
            last_error = exc
        except httpx.HTTPStatusError as exc:
            last_error = exc
            if exc.response.status_code < 500:
                break  # 4xx não é transitório — retry não ajudaria
        except ValidationError as exc:
            last_error = exc
            break  # contrato quebrado — retry não ajudaria

        if attempt < attempts - 1:
            backoff = _BACKOFF_SECONDS[min(attempt, len(_BACKOFF_SECONDS) - 1)]
            await asyncio.sleep(backoff * (1 + random.random() * 0.2))

    logger.warning("monitoring.fallback", service=service, error=str(last_error))
    return ServiceStatus(service=service, status="unknown", source="fallback")
