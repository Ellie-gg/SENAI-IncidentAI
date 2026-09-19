"""Servidor MCP (stdio) do IncidentAI.

Reexpõe as mesmas tools de `app/tools/core.py` — não reimplementa nada.
As docstrings e type hints abaixo SÃO o schema que um cliente MCP externo
enxerga (Claude Desktop, outro agente, `app/tools/registry.py` quando
`TOOLS_TRANSPORT=mcp`); mantenha-os precisos.

Rodar isolado (para inspecionar com um cliente MCP qualquer):
    python -m mcp_server.server
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from app.tools import core

mcp = FastMCP("incidentai-tools")


@mcp.tool()
async def get_service_status(service: str, environment: str = "production") -> dict:
    """Status atual, taxa de erro, latência p95 e histórico recente de um
    serviço monitorado pelo IncidentAI."""
    return await core.tool_get_service_status(service, environment)


@mcp.tool()
async def search_incident_history(query: str, service: str = "", limit: int = 3) -> dict:
    """Busca incidentes históricos similares por texto livre, opcionalmente
    filtrado por serviço."""
    return await core.tool_search_incident_history(query, service=service or None, limit=limit)


@mcp.tool()
async def search_runbooks(query: str, limit: int = 3) -> dict:
    """Busca trechos relevantes de runbooks internos por texto livre."""
    return await core.tool_search_runbooks(query, limit=limit)


if __name__ == "__main__":
    mcp.run(transport="stdio")
