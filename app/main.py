"""Factory da aplicação FastAPI + ciclo de vida (lifespan).

O lifespan mantém recursos de processo inteiro (checkpointer, grafo
compilado) — nunca recriados por request. `AsyncSqliteSaver` em particular
É um context manager: abri-lo por request reexecutaria `setup()` e fecharia
a conexão por baixo do request seguinte (bug documentado em
app/agent/checkpointer.py).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.agent.checkpointer import checkpointer_cm
from app.agent.graph import build_graph
from app.api.routes import router
from app.config import get_settings
from app.memory import db as memory_db
from app.observability.logger import configure_logging, get_logger
from app.tools import core as tools_core

logger = get_logger("incidentai")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(level=settings.log_level)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    logger.info(
        "incidentai.startup",
        environment=settings.environment,
        llm_provider=settings.llm_provider,
    )

    async with checkpointer_cm(str(settings.checkpoints_db_path)) as checkpointer:
        app.state.graph = build_graph(checkpointer=checkpointer)
        # Abre (e aplica o schema idempotente de) data/incidents.db cedo,
        # para falhar rápido no startup se FTS5 não estiver disponível em
        # vez de na primeira análise de incidente.
        memory_db.get_connection()

        try:
            yield
        finally:
            await tools_core.aclose()
            memory_db.close_connection()

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
