"""Rotas HTTP da aplicação.

/health (Fase 1) e /incidents/analyze (Fase 2: contrato validado; Fase 3:
execução real do grafo LangGraph). /incidents/{id}/approve chega na Fase 7.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Request, status

from app.agent.state import initial_state
from app.config import get_settings
from app.models.incident import IncidentRequest
from app.models.response import EvidenceBlock, IncidentResponse, RiskBlock

router = APIRouter()


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
        probable_cause=state.get("probable_cause", ""),
        confidence=state.get("confidence", 0.0),
        recommended_actions=state.get("recommended_actions", []),
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
async def analyze_incident(payload: IncidentRequest, request: Request) -> IncidentResponse:
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
    final_state = await graph.ainvoke(state, config=config)
    return _state_to_response(final_state, incident_id=incident_id, trace_id=trace_id)
