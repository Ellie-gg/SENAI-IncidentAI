"""Ponto único de chamada de tool a partir do grafo.

`TOOLS_TRANSPORT=inprocess` (default): chama `app/tools/core.py`
diretamente — sem dependência de subprocesso, é o que testes/CI usam.

`TOOLS_TRANSPORT=mcp`: chama a MESMA tool através do servidor MCP
(`mcp_server/server.py`), via stdio. Prova a integração real com o
protocolo MCP sem duplicar lógica — o servidor MCP é só um wrapper de
`core.py`. Cada chamada abre um subprocesso MCP novo (simples e correto;
uma sessão persistente ficaria no `app.state`, mas o ganho não compensa a
complexidade extra para o volume de chamadas deste projeto).
"""

from __future__ import annotations

import json
import sys
from typing import Any

from app.config import get_settings
from app.tools import core

_INPROCESS_TOOLS = {
    "get_service_status": core.tool_get_service_status,
    "search_incident_history": core.tool_search_incident_history,
    "search_runbooks": core.tool_search_runbooks,
}


async def call_tool(name: str, **kwargs: Any) -> dict:
    settings = get_settings()
    if settings.tools_transport == "mcp":
        return await _call_via_mcp(name, kwargs)

    func = _INPROCESS_TOOLS.get(name)
    if func is None:
        raise ValueError(f"Tool desconhecida: {name!r}")
    return await func(**kwargs)


async def _call_via_mcp(name: str, kwargs: dict[str, Any]) -> dict:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    # sys.executable (não a string "python"): garante que o subprocesso usa
    # o MESMO interpretador/venv que o processo atual — "python" na $PATH
    # poderia resolver para outra instalação sem as libs do projeto.
    params = StdioServerParameters(command=sys.executable, args=["-m", "mcp_server.server"])
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        result = await session.call_tool(name, arguments=kwargs)
        if result.isError:
            raise RuntimeError(f"MCP tool '{name}' retornou erro: {result.content}")
        text = result.content[0].text  # type: ignore[union-attr]
        return json.loads(text)
