"""Serviço mock de monitoramento — container HTTP separado da app principal.

Cenários determinísticos por nome de serviço (usados na demo e nos testes
E2E) + um endpoint de controle (`/_control/fail`) que força os próximos
`GET /services/{service}/status` a se comportarem mal (timeout, 500, JSON
fora do contrato) — é isso que `app/tools/monitoring_client.py` exercita
nos testes de resiliência (timeout→retry→fallback).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from app.models.monitoring import MetricPoint, ServiceStatus

app = FastAPI(title="IncidentAI Mock Monitoring", version="0.2.0")

_SCENARIOS: dict[str, dict] = {
    # Tendência de erro claramente crescente — é o caso canônico do
    # enunciado ([0.05, 0.09, 0.14] → "increasing") e o usado na demo.
    "payments-api": {
        "status": "degraded",
        "error_rate_series": [0.03, 0.05, 0.09, 0.14, 0.19],
        "latency_series": [400.0, 550.0, 900.0, 1600.0, 2350.0],
        "uptime_pct": 97.2,
    },
    "auth-api": {
        "status": "up",
        "error_rate_series": [0.01, 0.01, 0.01, 0.01, 0.01, 0.01],
        "latency_series": [120.0, 118.0, 125.0, 119.0, 121.0, 120.0],
        "uptime_pct": 99.98,
    },
    "legacy-batch": {
        "status": "down",
        "error_rate_series": [0.40, 0.60, 0.80, 0.95, 1.00],
        "latency_series": [5000.0, 5200.0, 6000.0, 7000.0, 8000.0],
        "uptime_pct": 62.0,
    },
}

_DEFAULT_SCENARIO = {
    "status": "up",
    "error_rate_series": [0.0, 0.0, 0.01, 0.0],
    "latency_series": [80.0, 82.0, 79.0, 81.0],
    "uptime_pct": 99.99,
}

FailMode = Literal["timeout", "500", "garbage"]
# Estado de controle em memória, por processo — só existe para permitir que
# testes/demo forcem os caminhos de falha do cliente sem precisar derrubar
# o container. Nunca usado como estado de negócio.
_fail_mode: FailMode | None = None


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "mock-monitoring"}


@app.post("/_control/fail")
async def set_fail_mode(mode: FailMode) -> dict:
    global _fail_mode
    _fail_mode = mode
    return {"fail_mode": _fail_mode}


@app.post("/_control/reset")
async def reset_fail_mode() -> dict:
    global _fail_mode
    _fail_mode = None
    return {"fail_mode": _fail_mode}


def _build_status(service: str) -> ServiceStatus:
    scenario = _SCENARIOS.get(service, _DEFAULT_SCENARIO)
    error_series = scenario["error_rate_series"]
    latency_series = scenario["latency_series"]
    now = datetime.now(UTC)
    n = len(error_series)
    history = [
        MetricPoint(
            ts=now - timedelta(minutes=5 * (n - i)),
            error_rate=er,
            latency_p95_ms=lat,
        )
        for i, (er, lat) in enumerate(zip(error_series, latency_series, strict=True))
    ]
    return ServiceStatus(
        service=service,
        status=scenario["status"],
        error_rate=error_series[-1],
        latency_p95_ms=latency_series[-1],
        uptime_pct=scenario["uptime_pct"],
        history=history,
        source="monitoring",
    )


@app.get("/services/{service}/status")
async def get_service_status(service: str, environment: str = "production"):
    del environment  # aceito por contrato; cenários aqui não variam por ambiente
    if _fail_mode == "timeout":
        await asyncio.sleep(10)  # bem acima do timeout de 3s do cliente
    if _fail_mode == "500":
        raise HTTPException(status_code=500, detail="mock-monitoring: falha simulada")
    if _fail_mode == "garbage":
        # Payload que não valida contra ServiceStatus — força ValidationError
        # no cliente (e prova que ele NÃO tenta retry nesse caso: contrato
        # quebrado não se resolve tentando de novo).
        return JSONResponse(content={"this_does_not": "match_the_schema"})
    return _build_status(service)
