"""Contrato de entrada: POST /incidents/analyze."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

Environment = Literal["production", "staging", "development"]
ApprovalDecision = Literal["approved", "rejected"]

MAX_LOGS = 200
MAX_LOG_LINE_LENGTH = 2000
MAX_DESCRIPTION_LENGTH = 4000


class IncidentRequest(BaseModel):
    """Payload recebido pela API. Validação de tamanho protege o pipeline
    (LLM, prompt, guardrails) de payloads hostis ou degenerados — um dos
    requisitos de segurança/robustez do enunciado."""

    service: str = Field(min_length=1, max_length=200)
    environment: Environment
    description: str = Field(min_length=1, max_length=MAX_DESCRIPTION_LENGTH)
    logs: list[str] = Field(default_factory=list, max_length=MAX_LOGS)

    @field_validator("service")
    @classmethod
    def _strip_service(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("service não pode ser vazio ou apenas espaços")
        return v

    @field_validator("description")
    @classmethod
    def _strip_description(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("description não pode ser vazio ou apenas espaços")
        return v

    @field_validator("logs")
    @classmethod
    def _truncate_log_lines(cls, v: list[str]) -> list[str]:
        # Trunca linhas individuais absurdamente longas em vez de rejeitar o
        # payload inteiro — mantém a API tolerante a logs verbosos de terceiros.
        return [line[:MAX_LOG_LINE_LENGTH] for line in v]

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "service": "payments-api",
                    "environment": "production",
                    "description": "API presenting database connection errors",
                    "logs": [
                        "ERROR database connection timeout",
                        "ERROR connection pool exhausted",
                        "WARN latency=2350ms",
                    ],
                }
            ]
        }
    }


class ApprovalRequest(BaseModel):
    """Corpo de POST /incidents/{id}/approve — decisão humana registrada
    para auditoria. A aplicação nunca executa a ação recomendada
    automaticamente; aprovar aqui é governança, não disparo de ação."""

    decision: ApprovalDecision
    actor: str = Field(min_length=1, max_length=200, description="Quem decidiu (ex.: 'jane.doe')")
    reason: str | None = Field(default=None, max_length=1000)
