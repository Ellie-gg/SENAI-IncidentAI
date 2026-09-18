"""Configuração global de testes.

LLM_PROVIDER=mock garante que a suíte inteira roda offline, sem chave de API
e sem chamadas de rede ao Gemini — obrigatório para CI e para qualquer
pessoa rodar `pytest` sem segredo nenhum configurado.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("MONITORING_ENABLED", "false")
os.environ.setdefault("TOOLS_TRANSPORT", "inprocess")

# Dados de teste (checkpoints, DB de incidentes) nunca tocam data/ do repo —
# cada processo de teste usa seu próprio diretório temporário.
_TEST_DATA_DIR = Path(tempfile.mkdtemp(prefix="incidentai-tests-"))
os.environ.setdefault("DATA_DIR", str(_TEST_DATA_DIR))
os.environ.setdefault("INCIDENTS_DB_PATH", str(_TEST_DATA_DIR / "incidents.db"))
os.environ.setdefault("CHECKPOINTS_DB_PATH", str(_TEST_DATA_DIR / "checkpoints.sqlite"))


@pytest.fixture
def app_client():
    """TestClient como context manager: dispara o lifespan (checkpointer,
    grafo compilado) — sem isso app.state.graph nunca é criado."""
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        yield client
