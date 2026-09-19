from __future__ import annotations

from app.memory import db
from app.memory.incident_repository import get_audit_trail
from app.observability.audit import record_execution_decisions


def test_blocked_incident_records_blocked_decision():
    conn = db.connect(":memory:")
    state = {
        "security_violation": True,
        "security_reasons": ["description contém padrão bloqueado: 'ignore previous instructions'"],
    }
    record_execution_decisions(conn, incident_id="INC-1", trace_id="t1", state=state)

    trail = get_audit_trail(conn, "INC-1")
    assert len(trail) == 1
    assert trail[0]["decision"] == "blocked"


def test_filtered_content_records_content_filtered_decision():
    conn = db.connect(":memory:")
    state = {
        "security_violation": False,
        "security_reasons": ["runbook 'x.md' filtrado (padrão bloqueado: 'drop database')"],
    }
    record_execution_decisions(conn, incident_id="INC-2", trace_id="t2", state=state)

    trail = get_audit_trail(conn, "INC-2")
    assert len(trail) == 1
    assert trail[0]["decision"] == "content_filtered"


def test_llm_parse_failure_records_fallback_used():
    conn = db.connect(":memory:")
    state = {"llm_parse_failed": True}
    record_execution_decisions(conn, incident_id="INC-3", trace_id="t3", state=state)

    trail = get_audit_trail(conn, "INC-3")
    decisions = [e["decision"] for e in trail]
    assert "fallback_used" in decisions


def test_pending_approval_records_requires_approval():
    conn = db.connect(":memory:")
    state = {"requires_human_approval": True, "action_class": "CHANGE", "security_violation": False}
    record_execution_decisions(conn, incident_id="INC-4", trace_id="t4", state=state)

    trail = get_audit_trail(conn, "INC-4")
    assert trail[0]["decision"] == "requires_approval"
    assert "CHANGE" in trail[0]["reason"]


def test_blocked_incident_does_not_also_record_requires_approval():
    """security_violation=True já implica bloqueio — não faz sentido
    também registrar 'aguardando aprovação' para algo que nunca vai rodar."""
    conn = db.connect(":memory:")
    state = {
        "security_violation": True,
        "security_reasons": ["x"],
        "requires_human_approval": True,
        "action_class": "DELETE",
    }
    record_execution_decisions(conn, incident_id="INC-5", trace_id="t5", state=state)

    trail = get_audit_trail(conn, "INC-5")
    decisions = [e["decision"] for e in trail]
    assert "requires_approval" not in decisions


def test_healthy_incident_records_nothing():
    conn = db.connect(":memory:")
    state = {
        "security_violation": False,
        "llm_parse_failed": False,
        "requires_human_approval": False,
    }
    record_execution_decisions(conn, incident_id="INC-6", trace_id="t6", state=state)

    trail = get_audit_trail(conn, "INC-6")
    assert trail == []


def test_audit_trail_is_ordered_chronologically():
    conn = db.connect(":memory:")
    record_execution_decisions(
        conn, incident_id="INC-7", trace_id="t7a", state={"llm_parse_failed": True}
    )
    record_execution_decisions(
        conn,
        incident_id="INC-7",
        trace_id="t7b",
        state={"requires_human_approval": True, "action_class": "CHANGE"},
    )
    trail = get_audit_trail(conn, "INC-7")
    assert len(trail) == 2
    assert trail[0]["decision"] == "fallback_used"
    assert trail[1]["decision"] == "requires_approval"
