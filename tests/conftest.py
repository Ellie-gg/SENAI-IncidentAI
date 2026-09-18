"""Configuração global de testes.

LLM_PROVIDER=mock garante que a suíte inteira roda offline, sem chave de API
e sem chamadas de rede ao Gemini — obrigatório para CI e para qualquer
pessoa rodar `pytest` sem segredo nenhum configurado.
"""

from __future__ import annotations

import os

os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("MONITORING_ENABLED", "false")
os.environ.setdefault("TOOLS_TRANSPORT", "inprocess")
