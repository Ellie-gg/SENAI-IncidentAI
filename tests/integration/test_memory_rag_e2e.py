"""Integração ponta a ponta da memória/RAG: seed real (mesmos dados do
scripts/seed_incidents.py) + runbooks reais de data/runbooks/, consultados
através de app/tools/core.py — a mesma porta de entrada que o grafo usa.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.memory import db
from app.memory.incident_repository import save_incident
from app.memory.ingest_runbooks import ingest_runbooks
from scripts.seed_incidents import INCIDENTS

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RUNBOOKS_DIR = REPO_ROOT / "data" / "runbooks"


@pytest.fixture
def seeded_conn():
    conn = db.connect(":memory:")
    for incident in INCIDENTS:
        save_incident(conn, **incident)
    ingest_runbooks(conn, RUNBOOKS_DIR)
    return conn


def test_seed_data_has_at_least_eight_incidents():
    assert len(INCIDENTS) >= 8


def test_real_runbooks_directory_ingests_successfully(seeded_conn):
    count = seeded_conn.execute("SELECT COUNT(*) AS n FROM runbook_chunks").fetchone()["n"]
    assert count > 0


async def test_search_finds_relevant_incident_for_payments_api_database_issue(seeded_conn):
    from app.memory import rag

    results = await rag.search_similar_incidents(
        seeded_conn,
        description="API presenting database connection errors",
        logs=["ERROR database connection timeout", "ERROR connection pool exhausted"],
        service="payments-api",
        limit=3,
    )
    assert len(results) >= 1
    assert any(r["category"] == "database_connectivity" for r in results)


async def test_search_finds_relevant_runbook_for_connection_pool(seeded_conn):
    from app.memory import rag

    results = await rag.search_runbooks(
        seeded_conn,
        description="connection pool exhausted database timeout",
        logs=[],
        service="payments-api",
        limit=3,
    )
    assert len(results) >= 1
    assert any("Connection Pool" in r["heading_path"] for r in results)


async def test_tool_core_search_incident_history_uses_shared_connection(monkeypatch, seeded_conn):
    """app/tools/core.py precisa usar a MESMA conexão singleton que a app
    usa — aqui trocamos o singleton por um já semeado para testar a porta
    de entrada real (a que o grafo chama) sem depender de arquivo em disco."""
    from app.memory import db as memory_db
    from app.tools import core

    monkeypatch.setattr(memory_db, "_connection", seeded_conn)
    try:
        result = await core.tool_search_incident_history(
            "database connection timeout connection pool exhausted", service="payments-api"
        )
        assert len(result["similar_incidents"]) >= 1

        runbooks = await core.tool_search_runbooks("connection pool exhausted")
        assert len(runbooks["runbook_chunks"]) >= 1
    finally:
        monkeypatch.setattr(memory_db, "_connection", None)
