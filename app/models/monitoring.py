"""Contrato compartilhado entre `app/tools/monitoring_client.py` (consumidor),
`mock_monitoring/main.py` (produtor real do container) e `mcp_server/`
(reexposição via MCP). Um único módulo, três consumidores — o contrato não
pode divergir entre client e servidor por definição.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ServiceStatusLiteral = Literal["up", "degraded", "down", "unknown"]


class MetricPoint(BaseModel):
    ts: datetime
    error_rate: float = Field(ge=0.0, le=1.0)
    latency_p95_ms: float = Field(ge=0.0)


class ServiceStatus(BaseModel):
    service: str
    status: ServiceStatusLiteral
    error_rate: float = Field(ge=0.0, le=1.0, default=0.0)
    latency_p95_ms: float = 0.0
    uptime_pct: float | None = None
    history: list[MetricPoint] = Field(default_factory=list)
    source: Literal["monitoring", "fallback"] = "monitoring"
