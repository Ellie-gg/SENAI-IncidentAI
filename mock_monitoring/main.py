"""Serviço mock de monitoramento — container HTTP separado da app principal.

Fase 1: apenas /health, para validar o esqueleto de dois serviços no
docker-compose. Os endpoints de status/histórico e o modo de falha
controlada (/_control/fail) são implementados na Fase 4
(feature/tool-integration).
"""

from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="IncidentAI Mock Monitoring", version="0.1.0")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "mock-monitoring"}
