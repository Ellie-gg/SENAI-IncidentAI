"""Testes da camada de busca (app/memory/rag.py) — a query nunca pode
quebrar a sintaxe do FTS5 mesmo com entrada adversarial, e a ordenação por
bm25() (negativo) precisa ser ASCENDENTE.
"""

from __future__ import annotations

import sqlite3

import pytest

from app.memory import db, rag
from app.memory.incident_repository import save_incident


def _seed(conn: sqlite3.Connection, incident_id: str, description: str, service: str = "x") -> None:
    save_incident(
        conn,
        incident_id=incident_id,
        service=service,
        environment="production",
        category="database_connectivity",
        severity="high",
        description=description,
        probable_cause="",
        resolution="",
        recommended_actions=[],
        logs_excerpt="",
    )


@pytest.fixture
def conn():
    connection = db.connect(":memory:")
    yield connection
    connection.close()


# --------------------------------------------------------------------------
# build_match_query — nunca deve deixar a sintaxe FTS5 quebrar
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "hostile_text",
    [
        'ignore previous instructions" OR 1=1 --',
        "NEAR(pool exhausted) AND *",
        "(unterminated paren",
        'quotes "inside" more "quotes"',
        "colon: dash-separated-terms",
    ],
)
def test_build_match_query_never_produces_invalid_fts_syntax(conn, hostile_text):
    query = rag.build_match_query(description=hostile_text, logs=[], service="payments-api")
    # Não pode levantar sqlite3.OperationalError — é a prova de que os
    # operadores do FTS5 foram neutralizados (tudo entre aspas).
    conn.execute("SELECT * FROM incidents_fts WHERE incidents_fts MATCH ?", (query,)).fetchall()


def test_build_match_query_falls_back_to_service_when_no_terms():
    query = rag.build_match_query(description="", logs=[], service="payments-api")
    assert query == '"payments-api"'


# --------------------------------------------------------------------------
# bm25() é NEGATIVO — ORDER BY precisa ser ASC. Trocar para DESC "conserta"
# a sintaxe e devolve os PIORES resultados primeiro, silenciosamente.
# --------------------------------------------------------------------------


def test_bm25_ordering_returns_best_match_first(conn):
    _seed(conn, "BEST", "pool pool pool pool exhausted connection pool issue")
    _seed(conn, "WORST", "a single mention of pool here and nothing else relevant")

    results = rag._search_incidents_sync(conn, match_query='"pool"', limit=5)

    assert len(results) == 2
    assert results[0]["incident_id"] == "BEST"  # maior relevância primeiro


# --------------------------------------------------------------------------
# Fallback determinístico quando a busca textual falha ou não acha nada
# --------------------------------------------------------------------------


async def test_search_similar_incidents_falls_back_on_operational_error(conn, monkeypatch):
    _seed(conn, "X", "totally unrelated content", service="payments-api")

    def boom(*args, **kwargs):
        raise sqlite3.OperationalError("simulated fts failure")

    monkeypatch.setattr(rag, "_search_incidents_sync", boom)

    results = await rag.search_similar_incidents(
        conn, description="irrelevant query text", logs=[], service="payments-api", limit=3
    )
    assert len(results) == 1
    assert results[0]["incident_id"] == "X"


async def test_search_similar_incidents_returns_empty_when_nothing_matches(conn):
    results = await rag.search_similar_incidents(
        conn, description="anything", logs=[], service="service-that-does-not-exist", limit=3
    )
    assert results == []


async def test_search_similar_incidents_finds_relevant_match_via_fts(conn):
    _seed(conn, "INC-1", "connection pool exhausted database timeout", service="payments-api")
    results = await rag.search_similar_incidents(
        conn,
        description="database connection pool exhausted",
        logs=["ERROR connection pool exhausted"],
        service="payments-api",
        limit=3,
    )
    assert len(results) == 1
    assert results[0]["incident_id"] == "INC-1"
