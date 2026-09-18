"""Checkpointer SQLite assíncrono — memória de execução do grafo (permite
retomar um thread, ex. depois de uma aprovação humana pendente).

`AsyncSqliteSaver.from_conn_string` é um async context manager: precisa ser
aberto UMA VEZ e mantido pelo tempo de vida do processo (ver app/main.py
lifespan). Abrir por request reexecutaria `setup()` e fecharia a conexão
por baixo do request seguinte — bug clássico documentado no design.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver


@asynccontextmanager
async def checkpointer_cm(path: str) -> AsyncIterator[BaseCheckpointSaver]:
    async with AsyncSqliteSaver.from_conn_string(path) as saver:
        yield saver
