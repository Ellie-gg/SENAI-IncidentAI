"""Rotas HTTP da aplicação.

Fase 1: apenas /health. As rotas de negócio (/incidents/analyze,
/incidents/{id}/approve) são adicionadas nas Fases 2, 3 e 7.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.config import get_settings

router = APIRouter()


@router.get("/health", tags=["ops"])
async def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.environment,
    }
