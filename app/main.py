"""Factory da aplicação FastAPI + ciclo de vida (lifespan).

O lifespan mantém recursos de processo inteiro (cliente HTTP, checkpointer,
grafo compilado, conexão de dados) — nunca recriados por request. Cada peça
é ligada incrementalmente conforme as fases avançam (ver comentários),
mantendo o app funcional (⁠`/health`⁠) desde a Fase 1.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.config import get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("incidentai")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    logger.info(
        "incidentai.startup",
        extra={"environment": settings.environment, "llm_provider": settings.llm_provider},
    )

    # Fase 2+: inicialização de httpx.AsyncClient (monitoring), banco SQLite
    # (memory/db.py), checkpointer (agent/checkpointer.py) e grafo compilado
    # (agent/graph.py) entram aqui, expostos via app.state.
    yield

    logger.info("incidentai.shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        description="Copiloto de SRE/DevOps com agente LangGraph.",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(router)
    return app


app = create_app()
