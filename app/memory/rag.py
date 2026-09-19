"""Busca leve estilo RAG sobre incidentes históricos e runbooks, via SQLite
FTS5 — sem vector DB, sem embeddings.

A parte delicada não é o ranking, é a CONSTRUÇÃO da query: texto de
usuário cru quebra a sintaxe `MATCH` do FTS5 em caracteres como `- " * : (`
e a palavra-chave `NEAR`. Por isso a query nunca interpola texto do
usuário diretamente — tokeniza, remove stopwords, pega os termos mais
frequentes e ENVOLVE CADA UM EM ASPAS, o que neutraliza todos os
operadores.

`bm25()` do SQLite retorna score NEGATIVO (mais negativo = melhor match) —
`ORDER BY rank` precisa ser ASCENDENTE. Trocar para `DESC` "conserta" a
sintaxe e devolve silenciosamente os PIORES resultados; há um teste
dedicado a essa armadilha em tests/unit/test_rag_query.py.
"""

from __future__ import annotations

import asyncio
import re
import sqlite3
from collections import Counter

_TOKEN_RE = re.compile(r"[A-Za-zÀ-ÿ0-9_]{3,}")
_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "that",
    "this",
    "are",
    "was",
    "were",
    "error",
    "warn",
    "info",
    "log",
    "logs",
    "para",
    "como",
    "uma",
    "com",
    "que",
    "não",
    "esta",
    "está",
    "dos",
    "das",
}


def build_match_query(
    *, description: str, logs: list[str], service: str, max_terms: int = 12
) -> str:
    """Nunca interpola texto cru — todo termo vai entre aspas, o que
    neutraliza qualquer operador FTS5 que apareça nos logs/descrição
    (inclusive tentativas deliberadas de injeção de sintaxe)."""
    text = " ".join([description, *logs[:20]]).lower()
    terms = [t for t in _TOKEN_RE.findall(text) if t not in _STOPWORDS]
    top_terms = [t for t, _ in Counter(terms).most_common(max_terms)]
    quoted = [f'"{t}"' for t in top_terms]
    service_term = f'"{service.lower()}"'
    if not quoted:
        return service_term
    return f"({service_term} OR {' OR '.join(quoted)})"


def _search_incidents_sync(conn: sqlite3.Connection, *, match_query: str, limit: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT i.*, bm25(incidents_fts, 3.0, 2.0, 2.0, 1.0, 1.5, 4.0) AS rank
        FROM incidents_fts
        JOIN incidents i ON i.rowid = incidents_fts.rowid
        WHERE incidents_fts MATCH ?
        ORDER BY rank ASC
        LIMIT ?
        """,
        (match_query, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def _search_runbooks_sync(conn: sqlite3.Connection, *, match_query: str, limit: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT c.*, bm25(runbooks_fts, 2.0, 3.0, 1.0) AS rank
        FROM runbooks_fts
        JOIN runbook_chunks c ON c.rowid = runbooks_fts.rowid
        WHERE runbooks_fts MATCH ?
        ORDER BY rank ASC
        LIMIT ?
        """,
        (match_query, limit),
    ).fetchall()
    return [dict(r) for r in rows]


async def search_similar_incidents(
    conn: sqlite3.Connection, *, description: str, logs: list[str], service: str, limit: int = 3
) -> list[dict]:
    match_query = build_match_query(description=description, logs=logs, service=service)
    try:
        results = await asyncio.to_thread(
            _search_incidents_sync, conn, match_query=match_query, limit=limit
        )
    except sqlite3.OperationalError:
        results = []

    if results:
        return results

    # Fallback determinístico (sem FTS) do PLAN.md v1 — garante que a demo
    # nunca fica sem evidência para um serviço/categoria conhecidos.
    from app.memory.incident_repository import search_similar

    return await asyncio.to_thread(
        search_similar, conn, service=service, category=None, limit=limit
    )


async def search_runbooks(
    conn: sqlite3.Connection, *, description: str, logs: list[str], service: str, limit: int = 3
) -> list[dict]:
    match_query = build_match_query(description=description, logs=logs, service=service)
    try:
        return await asyncio.to_thread(
            _search_runbooks_sync, conn, match_query=match_query, limit=limit
        )
    except sqlite3.OperationalError:
        return []
