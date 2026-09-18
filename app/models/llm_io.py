"""Schemas usados exclusivamente como `response_schema` do LLM (structured
output via Gemini). Mantidos deliberadamente "achatados": sem `Optional`,
sem `Union`/`dict[str, Any]`, sem modelos aninhados — a tradução de
JSON Schema do Gemini cobre só um subconjunto do que o Pydantic pode gerar,
e campos opcionais/aninhados tendem a ser descartados silenciosamente na
conversão. Ver docs/prompts/ para o motivo de cada restrição.

Nenhum campo destes dois modelos alimenta severidade, risco ou aprovação
diretamente — isso é regra determinística (app/risk, app/security). O LLM
decide categoria/causa/redação; a aplicação decide consequência.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

IncidentCategory = Literal[
    "database_connectivity",
    "latency_degradation",
    "memory_pressure",
    "deployment_regression",
    "dependency_failure",
    "auth_failure",
    "disk_capacity",
    "network",
    "unknown",
]


class AnalysisOut(BaseModel):
    """Saída estruturada do nó `analyze_incident`."""

    category: IncidentCategory
    probable_cause: str = Field(max_length=300)
    confidence: float = Field(ge=0.0, le=1.0)
    key_signals: list[str] = Field(max_length=5)


class RecommendationOut(BaseModel):
    """Saída estruturada do nó `generate_recommendation`."""

    summary: str = Field(max_length=500)
    recommended_actions: list[str] = Field(min_length=1, max_length=5)
