"""Fonte única das tools — funções `async` puras, sem import de LangGraph
nem de MCP. Três consumidores, zero reimplementação:

1. `app/agent/nodes.py` (via `app/tools/registry.py`, in-process)
2. `mcp_server/server.py` (wrappers finos, reexpõe via MCP)
3. testes
"""

from __future__ import annotations

import httpx

from app.config import get_settings
from app.memory import db as memory_db
from app.memory import rag
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
    """Busca incidentes históricos similares por texto (FTS5, com fallback
    determinístico por serviço/categoria — ver app/memory/rag.py)."""
    conn = memory_db.get_connection()
    results = await rag.search_similar_incidents(
        conn, description=query, logs=[], service=service or "", limit=limit
    )
    return {"similar_incidents": results}


async def tool_search_runbooks(query: str, limit: int = 3) -> dict:
    """Busca trechos relevantes de runbooks internos (FTS5)."""
    conn = memory_db.get_connection()
    results = await rag.search_runbooks(conn, description=query, logs=[], service="", limit=limit)
    return {"runbook_chunks": results}
