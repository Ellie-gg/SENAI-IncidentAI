"""State compartilhado do grafo LangGraph.

Regra que evita `InvalidUpdateError: At key 'X': Can receive only one value
per step`: toda chave escrita por mais de um nó no MESMO superstep precisa
de `Annotated[..., reducer]`. Isso acontece aqui porque `check_service_status`
e `search_incident_history` rodam em paralelo (fan-out a partir de
`analyze_incident`, fan-in em `assess_risk`) — ver app/agent/graph.py.

Chaves com reducer (escritas por >1 nó): errors, node_trace, tools_used,
metrics.
Chaves sem reducer: single-writer, last-write-wins é suficiente. Em
particular `iteration_count` é incrementado só em `analyze_incident` — um
reducer `operator.add` aqui contaria em dobro se algum dia dois nós
concorrentes escrevessem nele.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, TypedDict


def merge_dicts(a: dict[str, Any] | None, b: dict[str, Any] | None) -> dict[str, Any]:
    return {**(a or {}), **(b or {})}


class IncidentState(TypedDict, total=False):
    # ---- input (escrito uma vez, pela API, antes do primeiro nó) ----
    incident_id: str
    trace_id: str
    service: str
    environment: Literal["production", "staging", "development"]
    description: str
    logs: list[str]

    # ---- controle ----
    iteration_count: int  # escrito só em analyze_incident — sem reducer
    needs_reanalysis: bool
    is_valid: bool
    validation_errors: Annotated[list[str], operator.add]
    security_violation: bool
    security_reasons: Annotated[list[str], operator.add]
    terminal_reason: str | None

    # ---- saída do LLM (analyze_incident) ----
    category: str
    probable_cause: str
    confidence: float
    key_signals: list[str]
    llm_parse_failed: bool

    # ---- saída do LLM (generate_recommendation) ----
    summary: str
    recommended_actions: list[str]

    # ---- branch paralela A: check_service_status (tool HTTP) ----
    service_status: dict[str, Any] | None
    error_rate_series: list[float]
    latency_series: list[float]

    # ---- branch paralela B: search_incident_history (RAG) ----
    similar_incidents: list[dict[str, Any]]
    runbook_chunks: list[dict[str, Any]]

    # ---- escritas por MAIS DE UM nó -> reducer obrigatório ----
    errors: Annotated[list[dict[str, Any]], operator.add]
    node_trace: Annotated[list[dict[str, Any]], operator.add]
    tools_used: Annotated[list[str], operator.add]
    metrics: Annotated[dict[str, Any], merge_dicts]

    # ---- saída determinística (assess_risk / approval_check) ----
    severity: Literal["low", "medium", "high", "critical"]
    risk_score: int
    failure_risk: float
    trend: Literal["increasing", "stable", "decreasing"]
    trend_confidence: float
    action_class: Literal["READ", "ANALYZE", "RECOMMEND", "CHANGE", "DELETE"]
    requires_human_approval: bool


def initial_state(
    *,
    incident_id: str,
    trace_id: str,
    service: str,
    environment: str,
    description: str,
    logs: list[str],
) -> IncidentState:
    return IncidentState(
        incident_id=incident_id,
        trace_id=trace_id,
        service=service,
        environment=environment,  # type: ignore[typeddict-item]
        description=description,
        logs=logs,
        iteration_count=0,
        needs_reanalysis=False,
        errors=[],
        node_trace=[],
        tools_used=[],
        metrics={},
    )
