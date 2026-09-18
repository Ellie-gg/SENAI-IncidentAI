"""Configuração da aplicação via variáveis de ambiente.

Nenhuma credencial ou segredo tem valor default aqui — tudo vem do ambiente
(ou de um arquivo `.env` local, nunca versionado; ver `.env.example`).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- App ---
    app_name: str = "IncidentAI"
    environment: Literal["development", "staging", "production"] = "development"
    log_level: str = "INFO"

    # --- LLM ---
    # "gemini": chama a API real do Google AI Studio.
    # "mock": respostas determinísticas sem chamada externa (default — usado em testes/CI).
    # "mock_fail": sempre falha o parse estruturado, para exercitar a escada de fallback.
    llm_provider: Literal["gemini", "mock", "mock_fail"] = "mock"
    llm_model: str = "gemini-2.5-flash"
    google_api_key: str | None = Field(default=None, repr=False)

    # --- Tools / monitoring ---
    monitoring_base_url: str = "http://localhost:8081"
    monitoring_enabled: bool = True
    monitoring_timeout_seconds: float = 3.0
    monitoring_max_retries: int = 2

    # Transporte usado pelo grafo para chamar as tools: "inprocess" (padrão,
    # sem dependência de subprocesso — usado em testes/CI) ou "mcp" (via
    # servidor MCP stdio, prova a integração real).
    tools_transport: Literal["inprocess", "mcp"] = "inprocess"

    # --- Data ---
    data_dir: Path = BASE_DIR / "data"
    incidents_db_path: Path = BASE_DIR / "data" / "incidents.db"
    checkpoints_db_path: Path = BASE_DIR / "data" / "checkpoints.sqlite"
    runbooks_dir: Path = BASE_DIR / "data" / "runbooks"

    # --- Low-code / notificações ---
    n8n_webhook_url: str | None = None
    notify_min_severity: Literal["low", "medium", "high", "critical"] = "high"

    # --- Grafo ---
    max_iterations: int = 3
    recursion_limit: int = 25
    low_confidence_threshold: float = 0.4


@lru_cache
def get_settings() -> Settings:
    return Settings()
