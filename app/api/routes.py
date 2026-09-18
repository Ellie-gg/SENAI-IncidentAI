"""Rotas HTTP da aplicação.

Fase 1: /health. Fase 2: contrato de /incidents/analyze validado (ainda sem
o grafo — resposta 501 explícita). Fase 3 substitui o corpo pela invocação
real do LangGraph. Fase 7 adiciona /incidents/{id}/approve.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.config import get_settings
from app.models.incident import IncidentRequest

router = APIRouter()


@router.get("/health", tags=["ops"])
async def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.environment,
    }


@router.post("/incidents/analyze", tags=["incidents"], status_code=status.HTTP_200_OK)
async def analyze_incident(payload: IncidentRequest) -> dict:
    """Contrato validado pela Fase 2. A validação de payload (422 em erro)
    já está ativa; a execução do grafo é ligada na Fase 3."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=(
            f"Payload validado para o serviço '{payload.service}'. "
            "Execução do agente LangGraph ainda não ligada (chega na Fase 3)."
        ),
    )
