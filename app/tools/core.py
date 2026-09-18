"""Fonte única das tools — funções `async` puras, sem import de LangGraph
nem de MCP. Três consumidores, zero reimplementação:

1. `app/agent/nodes.py` (via `app/tools/registry.py`, in-process)
2. `mcp_server/server.py` (wrappers finos, reexpõe via MCP)
3. testes

Busca de histórico/runbooks aqui ainda é stub — a implementação real
(FTS5) chega na Fase 5 (`feature/memory-rag`), trocando só o corpo destas
duas funções.
"""

from __future__ import annotations

import httpx

from app.config import get_settings
from app.tools.monitoring_client import get_service_status as _http_get_service_status

_client: httpx.AsyncClient | None = None


async def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        settings = get_settings()
        _client = httpx.AsyncClient(base_url=settings.monitoring_base_url)
    return _client


async def aclose() -> None:
    """Chamado no shutdown da app (lifespan) e no fim dos testes."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def tool_get_service_status(service: str, environment: str = "production") -> dict:
    """Status atual, taxa de erro, latência p95 e histórico recente de um
    serviço monitorado. Resiliente: timeout/retry/fallback em
    monitoring_client.py — nunca levanta exceção."""
    client = await _get_client()
    status = await _http_get_service_status(client, service=service, environment=environment)
    return status.model_dump(mode="json")


async def tool_search_incident_history(
    query: str, service: str | None = None, limit: int = 3
) -> dict:
    """Busca incidentes históricos similares. [STUB Fase 4 — real na Fase 5
    / feature/memory-rag, via FTS5]."""
    del query, service, limit
    return {"similar_incidents": []}


async def tool_search_runbooks(query: str, limit: int = 3) -> dict:
    """Busca trechos relevantes de runbooks internos. [STUB Fase 4 — real
    na Fase 5 / feature/memory-rag, via FTS5]."""
    del query, limit
    return {"runbook_chunks": []}
