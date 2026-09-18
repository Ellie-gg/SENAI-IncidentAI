from __future__ import annotations

from pathlib import Path

from app.memory import db
from app.memory.ingest_runbooks import chunk_markdown, ingest_runbooks


def test_chunk_markdown_splits_on_headings_with_breadcrumb():
    # Cada seção precisa passar de MIN_CHUNK_CHARS (200) para não ser
    # fundida na seção anterior — replicando o tamanho real de um runbook.
    text = (
        "# Postgres Runbook\n\n"
        "Guia de triagem para incidentes de conectividade com o banco de "
        "dados Postgres em produção, cobrindo os cenários mais comuns.\n\n"
        "## Connection Pool\n\n"
        "Quando o número de conexões ativas se aproxima do max_size "
        "configurado no pool, novas requisições começam a falhar com "
        "timeout de conexão. Verifique o número de conexões ativas.\n\n"
        "### Exhaustion\n\n"
        "Os sintomas típicos nos logs são connection pool exhausted e "
        "database connection timeout. Mitigação: aumentar max_size "
        "temporariamente e considerar adicionar um pooler externo."
    )
    chunks = chunk_markdown(doc_path="postgres.md", doc_title="Postgres", text=text)

    headings = [c["heading_path"] for c in chunks]
    assert "Postgres Runbook > Connection Pool" in headings
    assert "Postgres Runbook > Connection Pool > Exhaustion" in headings
    assert all(c["doc_path"] == "postgres.md" for c in chunks)


def test_chunk_markdown_splits_long_sections():
    long_body = "Paragraph.\n\n" * 200  # bem acima de MAX_CHUNK_CHARS
    text = f"# Title\n\n## Section\n\n{long_body}"
    chunks = chunk_markdown(doc_path="x.md", doc_title="X", text=text)
    assert len(chunks) > 1
    assert all(len(c["content"]) <= 1200 + 200 for c in chunks)  # heading_path + folga


def test_chunk_markdown_merges_short_trailing_sections():
    text = "# Title\n\n## Long Section\n\n" + ("Real content. " * 40) + "\n\n## Tiny\n\nX."
    chunks = chunk_markdown(doc_path="x.md", doc_title="X", text=text)
    # a seção "Tiny" (curta demais) deve ter sido fundida no chunk anterior,
    # não virar um chunk próprio de baixa qualidade
    assert not any(c["heading_path"].endswith("Tiny") and len(c["content"]) < 50 for c in chunks)


def test_ingest_runbooks_is_idempotent(tmp_path: Path):
    runbooks_dir = tmp_path / "runbooks"
    runbooks_dir.mkdir()
    (runbooks_dir / "test.md").write_text(
        "# Test\n\n## Section One\n\nSome content that is reasonably long for a chunk here.",
        encoding="utf-8",
    )
    conn = db.connect(":memory:")

    written_first = ingest_runbooks(conn, runbooks_dir)
    written_second = ingest_runbooks(conn, runbooks_dir)  # arquivo não mudou

    assert written_first > 0
    assert written_second == 0  # content_hash igual -> nada reescrito

    count = conn.execute("SELECT COUNT(*) AS n FROM runbook_chunks").fetchone()["n"]
    assert count == written_first  # não duplicou


def test_ingest_runbooks_reingests_when_file_changes(tmp_path: Path):
    runbooks_dir = tmp_path / "runbooks"
    runbooks_dir.mkdir()
    md_path = runbooks_dir / "test.md"
    md_path.write_text(
        "# Test\n\n## A\n\nOriginal content long enough to be a chunk.", encoding="utf-8"
    )
    conn = db.connect(":memory:")
    ingest_runbooks(conn, runbooks_dir)

    md_path.write_text(
        "# Test\n\n## B\n\nChanged content, also long enough to be a chunk.", encoding="utf-8"
    )
    written = ingest_runbooks(conn, runbooks_dir)

    assert written > 0
    headings = [
        r["heading_path"]
        for r in conn.execute("SELECT heading_path FROM runbook_chunks").fetchall()
    ]
    assert any("B" in h for h in headings)
    assert not any(h.endswith(" > A") or h == "Test > A" for h in headings)


def test_ingest_runbooks_handles_missing_directory(tmp_path: Path):
    conn = db.connect(":memory:")
    written = ingest_runbooks(conn, tmp_path / "does-not-exist")
    assert written == 0
