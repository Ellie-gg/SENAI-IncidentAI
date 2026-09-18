"""Trilha de auditoria — segundo sinal de observabilidade (além dos logs
estruturados de `app/observability/logger.py`). Grava automaticamente as
decisões de governança de uma execução na tabela `audit_log`
(`app/memory/db.py`), correlacionadas por `incident_id`/`trace_id`.

`decision` é um de: `blocked`, `content_filtered`, `fallback_used`,
`requires_approval` — os mesmos rótulos citados no PLAN.md original.
"""

from __future__ import annotations

import sqlite3

from app.memory.incident_repository import save_audit_entry


def record_execution_decisions(
    conn: sqlite3.Connection, *, incident_id: str, trace_id: str, state: dict
) -> None:
    if state.get("security_violation"):
        reasons = "; ".join(state.get("security_reasons", [])) or "security_violation"
        save_audit_entry(
            conn,
            incident_id=incident_id,
            trace_id=trace_id,
            decision="blocked",
            actor="system",
            reason=reasons,
        )

    filtered = [r for r in state.get("security_reasons", []) if "filtrado" in r]
    for reason in filtered:
        save_audit_entry(
            conn,
            incident_id=incident_id,
            trace_id=trace_id,
            decision="content_filtered",
            actor="system",
            reason=reason,
        )

    if state.get("llm_parse_failed"):
        save_audit_entry(
            conn,
            incident_id=incident_id,
            trace_id=trace_id,
            decision="fallback_used",
            actor="system",
            reason="llm_structured_output_failed",
        )

    if state.get("requires_human_approval") and not state.get("security_violation"):
        save_audit_entry(
            conn,
            incident_id=incident_id,
            trace_id=trace_id,
            decision="requires_approval",
            actor="system",
            reason=f"action_class={state.get('action_class')}",
        )
