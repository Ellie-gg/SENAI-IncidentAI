"""Persistência de incidentes e eventos — camada fina sobre `sqlite3`.

Todas as funções aqui são síncronas (`sqlite3` é síncrono); chamadores
assíncronos devem envolver com `asyncio.to_thread` (ver `app/memory/rag.py`
e `app/agent/nodes.py`) para não bloquear o event loop.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime


def save_incident(
    conn: sqlite3.Connection,
    *,
    incident_id: str,
    service: str,
    environment: str,
    category: str,
    severity: str,
    description: str,
    probable_cause: str = "",
    resolution: str = "",
    recommended_actions: list[str] | None = None,
    logs_excerpt: str = "",
) -> None:
    conn.execute(
        """
        INSERT INTO incidents (
            incident_id, service, environment, category, severity, description,
            probable_cause, resolution, recommended_actions, logs_excerpt, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(incident_id) DO UPDATE SET
            category=excluded.category,
            severity=excluded.severity,
            probable_cause=excluded.probable_cause,
            resolution=excluded.resolution,
            recommended_actions=excluded.recommended_actions,
            logs_excerpt=excluded.logs_excerpt
        """,
        (
            incident_id,
            service,
            environment,
            category,
            severity,
            description,
            probable_cause,
            resolution,
            json.dumps(recommended_actions or []),
            logs_excerpt,
            datetime.now(UTC).isoformat(),
        ),
    )
    conn.commit()


def save_event(
    conn: sqlite3.Connection,
    *,
    incident_id: str,
    trace_id: str | None,
    node: str,
    status: str,
    duration_ms: float | None = None,
    detail: dict | None = None,
) -> None:
    conn.execute(
        """INSERT INTO incident_events
           (incident_id, trace_id, node, status, duration_ms, detail, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            incident_id,
            trace_id,
            node,
            status,
            duration_ms,
            json.dumps(detail or {}),
            datetime.now(UTC).isoformat(),
        ),
    )
    conn.commit()


def get_incident(conn: sqlite3.Connection, incident_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM incidents WHERE incident_id = ?", (incident_id,)).fetchone()
    return dict(row) if row else None


def search_similar(
    conn: sqlite3.Connection, *, service: str, category: str | None, limit: int = 5
) -> list[dict]:
    """Fallback determinístico (sem FTS) — usado quando a busca textual
    (`app/memory/rag.py`) não retorna nada, garantindo que a demo nunca
    fica sem evidência para um serviço/categoria conhecidos."""
    if category:
        rows = conn.execute(
            "SELECT * FROM incidents WHERE service = ? OR category = ? "
            "ORDER BY created_at DESC LIMIT ?",
            (service, category, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM incidents WHERE service = ? ORDER BY created_at DESC LIMIT ?",
            (service, limit),
        ).fetchall()
    return [dict(r) for r in rows]
