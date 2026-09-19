"""Ingestão idempotente de runbooks markdown para `app/memory/rag.py`.

Chunking por seções H1/H2/H3, com `heading_path` (breadcrumb, ex.
"Postgres Runbook > Connection Pool > Exhaustion") prefixado ao conteúdo
indexado — assim os termos do breadcrumb também entram na busca textual.
`content_hash` por arquivo evita reingestão quando o arquivo não mudou:
seguro rodar em todo start de container (`scripts/seed_incidents.py`).
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)
MAX_CHUNK_CHARS = 1200
MIN_CHUNK_CHARS = 200


def _split_sections(text: str) -> list[tuple[str, str]]:
    """Retorna [(heading_path, conteúdo)] cortando o markdown em H1/H2/H3."""
    matches = list(_HEADING_RE.finditer(text))
    if not matches:
        return [("", text.strip())] if text.strip() else []

    sections: list[tuple[str, str]] = []
    stack: list[str] = []
    for i, m in enumerate(matches):
        level = len(m.group(1))
        title = m.group(2).strip()
        stack = [*stack[: level - 1], title]
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if body:
            sections.append((" > ".join(stack), body))
    return sections


def _split_long_section(body: str) -> list[str]:
    if len(body) <= MAX_CHUNK_CHARS:
        return [body]
    paragraphs = [p for p in body.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current = ""
    for p in paragraphs:
        if len(current) + len(p) + 2 <= MAX_CHUNK_CHARS:
            current = f"{current}\n\n{p}".strip()
        else:
            if current:
                chunks.append(current)
            current = p
    if current:
        chunks.append(current)
    return chunks or [body[:MAX_CHUNK_CHARS]]


def chunk_markdown(*, doc_path: str, doc_title: str, text: str) -> list[dict]:
    chunks: list[dict] = []
    idx = 0
    for heading_path, body in _split_sections(text):
        for piece in _split_long_section(body):
            content = f"{heading_path}\n{piece}" if heading_path else piece
            if len(content) < MIN_CHUNK_CHARS and chunks:
                # Seção curta demais para valer um chunk próprio — funde no
                # chunk anterior do mesmo documento em vez de indexar ruído.
                chunks[-1]["content"] = f"{chunks[-1]['content']}\n\n{content}"
                continue
            chunks.append(
                {
                    "doc_path": doc_path,
                    "doc_title": doc_title,
                    "heading_path": heading_path,
                    "chunk_index": idx,
                    "content": content,
                }
            )
            idx += 1
    return chunks


def ingest_runbooks(conn: sqlite3.Connection, runbooks_dir: Path) -> int:
    """Idempotente: recalcula `content_hash` por arquivo e só reescreve
    quando o conteúdo mudou. Retorna quantos chunks foram (re)escritos."""
    if not runbooks_dir.exists():
        return 0

    written = 0
    for md_path in sorted(runbooks_dir.glob("*.md")):
        text = md_path.read_text(encoding="utf-8")
        content_hash = hashlib.sha1(text.encode("utf-8")).hexdigest()  # noqa: S324 — não é criptográfico
        doc_title = md_path.stem.replace("-", " ").replace("_", " ").title()

        existing = conn.execute(
            "SELECT content_hash FROM runbook_chunks WHERE doc_path = ? LIMIT 1",
            (md_path.name,),
        ).fetchone()
        if existing and existing["content_hash"] == content_hash:
            continue  # arquivo não mudou desde a última ingestão

        conn.execute("DELETE FROM runbook_chunks WHERE doc_path = ?", (md_path.name,))
        chunks = chunk_markdown(doc_path=md_path.name, doc_title=doc_title, text=text)
        now = datetime.now(UTC).isoformat()
        for chunk in chunks:
            chunk_id = hashlib.sha1(  # noqa: S324
                f"{chunk['doc_path']}:{chunk['chunk_index']}".encode()
            ).hexdigest()
            conn.execute(
                """INSERT INTO runbook_chunks
                   (chunk_id, doc_path, doc_title, heading_path, chunk_index,
                    content, services, content_hash, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    chunk_id,
                    chunk["doc_path"],
                    chunk["doc_title"],
                    chunk["heading_path"],
                    chunk["chunk_index"],
                    chunk["content"],
                    "",
                    content_hash,
                    now,
                ),
            )
            written += 1
    conn.commit()
    return written
