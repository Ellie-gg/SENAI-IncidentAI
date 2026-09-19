"""Rotas HTTP da aplicação.

/health (Fase 1) e /incidents/analyze (Fase 2: contrato validado; Fase 3:
execução real do grafo LangGraph). /incidents/{id}/approve (Fase 7):
registra uma decisão humana para auditoria — a aplicação NUNCA executa a
ação recomendada automaticamente, aprovar aqui é governança, não disparo.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status

from app.agent.state import initial_state
from app.config import get_settings
from app.memory import db as memory_db
from app.memory.incident_repository import get_audit_trail, save_audit_entry
from app.models.incident import ApprovalRequest, IncidentRequest
from app.models.response import EvidenceBlock, IncidentResponse, RiskBlock
from app.observability import audit as audit_module
from app.observability import metrics as metrics_module
from app.observability.logger import get_logger, log_execution
from app.security.guardrails import redact_secrets
from app.services.notifier import notify_incident

router = APIRouter()
logger = get_logger("incidentai.api")


@router.get("/health", tags=["ops"])
async def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.environment,
    }


def _new_incident_id() -> str:
    return f"INC-{uuid.uuid4().hex[:6].upper()}"


def _state_to_response(state: dict, *, incident_id: str, trace_id: str) -> IncidentResponse:
    """Todo caminho terminal do grafo (bloqueado, pendente de aprovação,
    concluído, degradado) passa por um nó `finalize_*` que garante os
    campos abaixo — este mapeamento nunca precisa tratar state parcial."""
    service_status = state.get("service_status") or {}
    return IncidentResponse(
        incident_id=incident_id,
        trace_id=trace_id,
        category=state.get("category", "unknown"),
        severity=state.get("severity", "low"),
        probable_cause=redact_secrets(state.get("probable_cause", "")),
        confidence=state.get("confidence", 0.0),
        recommended_actions=[redact_secrets(a) for a in state.get("recommended_actions", [])],
        risk=RiskBlock(
            score=state.get("risk_score", 0),
            failure_risk=state.get("failure_risk", 0.0),
            trend=state.get("trend", "stable"),
            trend_confidence=state.get("trend_confidence", 0.0),
        ),
        action_class=state.get("action_class", "READ"),
        requires_human_approval=state.get("requires_human_approval", False),
        evidence=EvidenceBlock(
            similar_incidents=[
                i.get("incident_id", "") for i in state.get("similar_incidents", [])
            ],
            runbooks=[c.get("heading_path", "") for c in state.get("runbook_chunks", [])],
            service_status=service_status.get("status", "unknown"),
            monitoring_source=service_status.get("source", "fallback"),
        ),
        security_violation=state.get("security_violation", False),
        degraded=bool(state.get("llm_parse_failed"))
        or state.get("terminal_reason") == "completed_degraded",
        terminal_reason=state.get("terminal_reason"),
    )


@router.post("/incidents/analyze", tags=["incidents"], status_code=status.HTTP_200_OK)
async def analyze_incident(
    payload: IncidentRequest, request: Request, background_tasks: BackgroundTasks
) -> IncidentResponse:
    settings = get_settings()
    incident_id = _new_incident_id()
    trace_id = uuid.uuid4().hex

    state = initial_state(
        incident_id=incident_id,
        trace_id=trace_id,
        service=payload.service,
        environment=payload.environment,
        description=payload.description,
        logs=payload.logs,
    )
    graph = request.app.state.graph
    config = {
        "configurable": {"thread_id": incident_id},
        "recursion_limit": settings.recursion_limit,
    }

    logger.info(
        "incident.received",
        trace_id=trace_id,
        incident_id=incident_id,
        service=payload.service,
        environment=payload.environment,
    )
    try:
        final_state = await graph.ainvoke(state, config=config)
    except Exception:
        # Rede de segurança final: nenhum nó do grafo deveria propagar
        # exceção (cada um trata e degrada), mas se algo inesperado
        # acontecer, a API nunca devolve um 500 sem contexto — loga
        # correlacionado por trace_id antes de responder.
        logger.error("incident.analyze_failed", trace_id=trace_id, incident_id=incident_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Falha inesperada ao analisar o incidente (trace_id={trace_id}).",
        ) from None

    log_execution(incident_id=incident_id, trace_id=trace_id, state=final_state)
    conn = memory_db.get_connection()
    audit_module.record_execution_decisions(
        conn, incident_id=incident_id, trace_id=trace_id, state=final_state
    )

    # Notificação (n8n) roda em background — nunca atrasa nem quebra a
    # resposta da análise, e só dispara acima do limiar de severidade
    # configurado (NOTIFY_MIN_SEVERITY).
    background_tasks.add_task(
        notify_incident,
        incident_id=incident_id,
        trace_id=trace_id,
        service=payload.service,
        environment=payload.environment,
        severity=final_state.get("severity", "low"),
        category=final_state.get("category", "unknown"),
        probable_cause=redact_secrets(final_state.get("probable_cause", "")),
        requires_human_approval=final_state.get("requires_human_approval", False),
    )

    return _state_to_response(final_state, incident_id=incident_id, trace_id=trace_id)


@router.get("/incidents/{incident_id}/audit", tags=["incidents", "ops"])
async def get_incident_audit_trail(incident_id: str) -> dict:
    """Reconstrói as decisões de governança de um incidente — o segundo
    sinal de observabilidade, correlacionado por incident_id/trace_id com
    os logs estruturados emitidos em log_execution()."""
    conn = memory_db.get_connection()
    entries = get_audit_trail(conn, incident_id)
    return {"incident_id": incident_id, "entries": entries}


@router.get("/metrics", tags=["ops"])
async def get_metrics() -> dict:
    return metrics_module.get_registry().snapshot()


@router.post("/incidents/{incident_id}/approve", tags=["incidents"])
async def approve_incident(incident_id: str, payload: ApprovalRequest, request: Request) -> dict:
    graph = request.app.state.graph
    config = {"configurable": {"thread_id": incident_id}}
    snapshot = await graph.aget_state(config)
    state = snapshot.values

    if not state:
        raise HTTPException(status_code=404, detail=f"Incidente '{incident_id}' não encontrado.")
    if not state.get("requires_human_approval"):
        raise HTTPException(
            status_code=409,
            detail=f"Incidente '{incident_id}' não está aguardando aprovação humana.",
        )

    conn = memory_db.get_connection()
    save_audit_entry(
        conn,
        incident_id=incident_id,
        trace_id=state.get("trace_id"),
        decision=payload.decision,
        actor=payload.actor,
        reason=payload.reason,
    )

    return {
        "incident_id": incident_id,
        "decision": payload.decision,
        "actor": payload.actor,
        "action_class": state.get("action_class"),
        "note": (
            "Decisão registrada para auditoria. A aplicação nunca executa a ação "
            "recomendada automaticamente — aprovação aqui é governança, não disparo."
        ),
    }
