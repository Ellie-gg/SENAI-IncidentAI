"""Testes do dispatcher de tools: 'inprocess' (default, sem subprocesso —
usado em testes/CI) e 'mcp' (via servidor MCP real, stdio) — os dois falam
com a MESMA implementação em app/tools/core.py, só o transporte muda.
"""

from __future__ import annotations

import pytest

from app.config import get_settings
from app.tools.registry import call_tool


async def test_inprocess_dispatch_calls_core_directly():
    result = await call_tool("get_service_status", service="payments-api", environment="production")
    assert result["service"] == "payments-api"
    # MONITORING_ENABLED=false por padrão nos testes (tests/conftest.py)
    assert result["status"] == "unknown"
    assert result["source"] == "fallback"


async def test_inprocess_dispatch_unknown_tool_raises():
    with pytest.raises(ValueError):
        await call_tool("does_not_exist")


async def test_mcp_transport_reaches_the_same_underlying_tool(monkeypatch):
    """Sobe um subprocesso MCP real (mcp_server/server.py) e chama a tool
    por stdio — prova a integração de verdade com o protocolo, não só o
    wrapper Python. Mais lento que o caminho inprocess (custo de subir um
    processo Python novo) — aceitável para uma suíte pequena."""
    monkeypatch.setenv("TOOLS_TRANSPORT", "mcp")
    monkeypatch.setenv("MONITORING_ENABLED", "false")
    get_settings.cache_clear()
    try:
        result = await call_tool("get_service_status", service="auth-api", environment="production")
        assert result["service"] == "auth-api"
        assert result["status"] == "unknown"
        assert result["source"] == "fallback"
    finally:
        get_settings.cache_clear()
