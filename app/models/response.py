"""Contrato de saída: resposta estruturada de POST /incidents/analyze.

Todo campo aqui é preenchido pelo grafo (app/agent) — este módulo não
depende de app.agent para evitar import circular; ele é o "shape" que o
grafo é obrigado a produzir em qualquer caminho terminal (bloqueado,
pendente de aprovação, concluído, degradado).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Severity = Literal["low", "medium", "high", "critical"]
Trend = Literal["increasing", "stable", "decreasing"]
ActionClass = Literal["READ", "ANALYZE", "RECOMMEND", "CHANGE", "DELETE"]


class RiskBlock(BaseModel):
    score: int = Field(ge=0, description="Score aditivo determinístico (ver app/risk/scoring.py)")
    failure_risk: float = Field(ge=0.0, le=1.0, description="Probabilidade estimada de falha")
    trend: Trend
    trend_confidence: float = Field(ge=0.0, le=1.0)


class EvidenceBlock(BaseModel):
    similar_incidents: list[str] = Field(
        default_factory=list, description="IDs de incidentes similares"
    )
    runbooks: list[str] = Field(
        default_factory=list, description="Títulos/seções de runbook consultados"
    )
    service_status: str = Field(default="unknown")
    monitoring_source: Literal["monitoring", "fallback"] = "fallback"


class IncidentResponse(BaseModel):
    incident_id: str
    trace_id: str

    category: str
    severity: Severity
    probable_cause: str
    confidence: float = Field(ge=0.0, le=1.0)
    recommended_actions: list[str] = Field(default_factory=list)

    risk: RiskBlock
    action_class: ActionClass
    requires_human_approval: bool

    evidence: EvidenceBlock

    security_violation: bool = False
    degraded: bool = Field(
        default=False,
        description="True quando a análise do LLM falhou e a resposta usa fallback determinístico",
    )
    terminal_reason: str | None = Field(
        default=None,
        description="Motivo do término quando não é o caminho feliz (ex.: 'security_blocked', 'pending_approval')",
    )
