"""Conexão e schema do banco de dados SQLite (memória/RAG + auditoria).

Um único arquivo (`data/incidents.db`), WAL habilitado — importante rodando
via docker-compose em volume nomeado (bind mount do Windows é fonte comum
de "database is locked"). FTS5 é checado no startup com mensagem clara em
vez de deixar `no such module: fts5` estourar na primeira query de busca.

`get_connection()` é um singleton preguiçoso de processo — mesmo padrão do
cliente HTTP em `app/tools/core.py`. Funciona tanto para a API (processo
único) quanto para o servidor MCP (processo separado, sua própria conexão;
SQLite com WAL suporta múltiplos processos lendo/escrevendo).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

_SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS incidents (
    incident_id TEXT PRIMARY KEY,
    service TEXT NOT NULL,
    environment TEXT NOT NULL,
    category TEXT,
    severity TEXT,
    description TEXT NOT NULL,
    probable_cause TEXT,
    resolution TEXT,
    recommended_actions TEXT,  -- JSON array
    logs_excerpt TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_incidents_service ON incidents(service);
CREATE INDEX IF NOT EXISTS idx_incidents_category ON incidents(category);

CREATE VIRTUAL TABLE IF NOT EXISTS incidents_fts USING fts5(
    description, probable_cause, resolution, logs_excerpt, category, service,
    content='incidents', content_rowid='rowid',
    tokenize="unicode61 remove_diacritics 2"
);

CREATE TRIGGER IF NOT EXISTS incidents_ai AFTER INSERT ON incidents BEGIN
    INSERT INTO incidents_fts(rowid, description, probable_cause, resolution, logs_excerpt, category, service)
    VALUES (new.rowid, new.description, new.probable_cause, new.resolution, new.logs_excerpt, new.category, new.service);
END;
CREATE TRIGGER IF NOT EXISTS incidents_ad AFTER DELETE ON incidents BEGIN
    INSERT INTO incidents_fts(incidents_fts, rowid, description, probable_cause, resolution, logs_excerpt, category, service)
    VALUES ('delete', old.rowid, old.description, old.probable_cause, old.resolution, old.logs_excerpt, old.category, old.service);
END;
CREATE TRIGGER IF NOT EXISTS incidents_au AFTER UPDATE ON incidents BEGIN
    INSERT INTO incidents_fts(incidents_fts, rowid, description, probable_cause, resolution, logs_excerpt, category, service)
    VALUES ('delete', old.rowid, old.description, old.probable_cause, old.resolution, old.logs_excerpt, old.category, old.service);
    INSERT INTO incidents_fts(rowid, description, probable_cause, resolution, logs_excerpt, category, service)
    VALUES (new.rowid, new.description, new.probable_cause, new.resolution, new.logs_excerpt, new.category, new.service);
END;

CREATE TABLE IF NOT EXISTS runbook_chunks (
    chunk_id TEXT PRIMARY KEY,
    doc_path TEXT NOT NULL,
    doc_title TEXT,
    heading_path TEXT,
    chunk_index INTEGER,
    content TEXT NOT NULL,
    services TEXT,
    content_hash TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS runbooks_fts USING fts5(
    doc_title, heading_path, content,
    content='runbook_chunks', content_rowid='rowid',
    tokenize="unicode61 remove_diacritics 2"
);

CREATE TRIGGER IF NOT EXISTS runbooks_ai AFTER INSERT ON runbook_chunks BEGIN
    INSERT INTO runbooks_fts(rowid, doc_title, heading_path, content)
    VALUES (new.rowid, new.doc_title, new.heading_path, new.content);
END;
CREATE TRIGGER IF NOT EXISTS runbooks_ad AFTER DELETE ON runbook_chunks BEGIN
    INSERT INTO runbooks_fts(runbooks_fts, rowid, doc_title, heading_path, content)
    VALUES ('delete', old.rowid, old.doc_title, old.heading_path, old.content);
END;
CREATE TRIGGER IF NOT EXISTS runbooks_au AFTER UPDATE ON runbook_chunks BEGIN
    INSERT INTO runbooks_fts(runbooks_fts, rowid, doc_title, heading_path, content)
    VALUES ('delete', old.rowid, old.doc_title, old.heading_path, old.content);
    INSERT INTO runbooks_fts(rowid, doc_title, heading_path, content)
    VALUES (new.rowid, new.doc_title, new.heading_path, new.content);
END;

CREATE TABLE IF NOT EXISTS incident_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id TEXT NOT NULL,
    trace_id TEXT,
    node TEXT NOT NULL,
    status TEXT NOT NULL,
    duration_ms REAL,
    detail TEXT,  -- JSON
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_incident_events_incident ON incident_events(incident_id);

-- Escrito a partir da Fase 8 (feature/observability) — schema criado aqui
-- para manter toda a migração num único lugar.
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id TEXT NOT NULL,
    trace_id TEXT,
    decision TEXT NOT NULL,  -- blocked | approved | requires_approval | fallback_used | llm_parse_failed
    actor TEXT NOT NULL,     -- 'system' | 'human:<id>'
    reason TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_log_incident ON audit_log(incident_id);
"""


def check_fts5_available(conn: sqlite3.Connection) -> None:
    row = conn.execute(
        "SELECT 1 FROM pragma_compile_options WHERE compile_options LIKE 'ENABLE_FTS5'"
    ).fetchone()
    if row is None:
        raise RuntimeError(
            "O SQLite deste ambiente foi compilado sem suporte a FTS5 — a busca de "
            "memória/RAG (app/memory/rag.py) não vai funcionar. Use uma build de "
            "Python/SQLite com FTS5 habilitado (CPython padrão no Linux/Windows já traz)."
        )


def connect(path: str | Path) -> sqlite3.Connection:
    """Abre uma conexão nova, aplica o schema (idempotente) e valida FTS5.
    Uso direto em testes/scripts; a API usa `get_connection()` (singleton)."""
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    check_fts5_available(conn)
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn


_connection: sqlite3.Connection | None = None


def get_connection() -> sqlite3.Connection:
    """Singleton preguiçoso de processo — reaproveitado por todas as
    chamadas de tool no mesmo processo (API ou servidor MCP)."""
    global _connection
    if _connection is None:
        from app.config import get_settings

        settings = get_settings()
        _connection = connect(settings.incidents_db_path)
    return _connection


def close_connection() -> None:
    global _connection
    if _connection is not None:
        _connection.close()
        _connection = None
