"""Nós do grafo.

Marcação `[STUB Fase N]` indica nós cuja lógica real chega em fase
posterior — o wiring do grafo (topologia, paralelismo, reducers) já é
definitivo desde a Fase 3; só o corpo da função é substituído depois,
mantendo a mesma assinatura `async def node(state) -> dict`.

`validate_input`, `analyze_incident` e `generate_recommendation` já são
implementações reais desta fase (usam o LLM configurável via
`LLM_PROVIDER`, com `mock` como default determinístico e offline).
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from app.agent.prompts import build_analysis_prompt, build_recommendation_prompt
from app.agent.state import IncidentState
from app.config import get_settings
from app.models.llm_io import AnalysisOut, RecommendationOut
from app.services.llm import default_actions_for_category, get_llm, structured_with_fallback


def _trace(node: str, t0: float, status: str, **extra: Any) -> dict:
    duration_ms = round((time.perf_counter() - t0) * 1000, 2)
    return {"node_trace": [{"node": node, "status": status, "duration_ms": duration_ms, **extra}]}


# --------------------------------------------------------------------------
# validate_input — real
# --------------------------------------------------------------------------


async def validate_input(state: IncidentState) -> dict:
    t0 = time.perf_counter()
    errors: list[str] = []
    if not state.get("service", "").strip():
        errors.append("service vazio")
    if not state.get("description", "").strip():
        errors.append("description vazia")
    if state.get("environment") not in ("production", "staging", "development"):
        errors.append("environment inválido")

    is_valid = not errors
    return {
        "is_valid": is_valid,
        "validation_errors": errors,
        **_trace("validate_input", t0, "ok" if is_valid else "invalid", errors=errors),
    }


# --------------------------------------------------------------------------
# security_check — [STUB Fase 3, real na Fase 7 / feature/security]
# --------------------------------------------------------------------------


async def security_check(state: IncidentState) -> dict:
    t0 = time.perf_counter()
    return {
        "security_violation": False,
        "security_reasons": [],
        **_trace("security_check", t0, "ok"),
    }


# --------------------------------------------------------------------------
# analyze_incident — real (LLM configurável)
# --------------------------------------------------------------------------


async def analyze_incident(state: IncidentState) -> dict:
    t0 = time.perf_counter()
    settings = get_settings()
    client = get_llm()
    iteration = state.get("iteration_count", 0) + 1

    prompt = build_analysis_prompt(
        service=state["service"],
        environment=state["environment"],
        description=state["description"],
        logs=state.get("logs", []),
        # Só há evidência de branches paralelas a partir da 2a passada
        # (depois de um fan-in anterior) — é isso que torna um retry
        # potencialmente diferente da 1a tentativa, não um no-op.
        similar_incidents=state.get("similar_incidents") if iteration > 1 else None,
        service_status=state.get("service_status") if iteration > 1 else None,
    )
    result, degraded = await structured_with_fallback(client, AnalysisOut, prompt)

    if degraded or result is None:
        return {
            "category": "unknown",
            "probable_cause": "Análise automática indisponível; revisão manual necessária.",
            "confidence": 0.2,
            "key_signals": [],
            "llm_parse_failed": True,
            "needs_reanalysis": iteration < settings.max_iterations,
            "iteration_count": iteration,
            "tools_used": ["llm:analyze"],
            "errors": [{"node": "analyze_incident", "error": "llm_structured_output_failed"}],
            **_trace("analyze_incident", t0, "degraded"),
        }

    low_confidence = result.confidence < settings.low_confidence_threshold
    return {
        "category": result.category,
        "probable_cause": result.probable_cause,
        "confidence": result.confidence,
        "key_signals": result.key_signals,
        "llm_parse_failed": False,
        # só tenta de novo se ainda não usamos a evidência de retry desta vez
        "needs_reanalysis": low_confidence
        and iteration == 1
        and iteration < settings.max_iterations,
        "iteration_count": iteration,
        "tools_used": ["llm:analyze"],
        **_trace("analyze_incident", t0, "ok", confidence=result.confidence),
    }


# --------------------------------------------------------------------------
# check_service_status — [STUB Fase 3, real na Fase 4 / feature/tool-integration]
# Roda em paralelo com search_incident_history (fan-out a partir de
# analyze_incident). Precisa ser async e não-bloqueante — asyncio.sleep aqui
# simula I/O de rede; a Fase 4 troca por uma chamada httpx real ao container
# mock-monitoring, mantendo a mesma assinatura e o mesmo contrato de saída.
# --------------------------------------------------------------------------


async def check_service_status(state: IncidentState) -> dict:
    t0 = time.perf_counter()
    try:
        await asyncio.sleep(0.05)  # placeholder de I/O — substituído na Fase 4
        status = {
            "service": state["service"],
            "status": "unknown",
            "error_rate": 0.0,
            "latency_p95_ms": 0.0,
            "history": [],
            "source": "fallback",
        }
        return {
            "service_status": status,
            "error_rate_series": [],
            "latency_series": [],
            "tools_used": ["tool:check_service_status"],
            **_trace("check_service_status", t0, "stub"),
        }
    except Exception as exc:  # noqa: BLE001 — nó paralelo nunca propaga exceção
        return {
            "service_status": None,
            "errors": [{"node": "check_service_status", "error": str(exc)}],
            **_trace("check_service_status", t0, "error", error=str(exc)),
        }


# --------------------------------------------------------------------------
# search_incident_history — [STUB Fase 3, real na Fase 5 / feature/memory-rag]
# Roda em paralelo com check_service_status. asyncio.sleep simula o custo de
# I/O que a Fase 5 substitui por uma consulta FTS5 (sqlite, via
# asyncio.to_thread para não bloquear o event loop).
# --------------------------------------------------------------------------


async def search_incident_history(state: IncidentState) -> dict:
    t0 = time.perf_counter()
    try:
        await asyncio.sleep(0.05)  # placeholder de I/O — substituído na Fase 5
        return {
            "similar_incidents": [],
            "runbook_chunks": [],
            "tools_used": ["memory:search_incident_history"],
            **_trace("search_incident_history", t0, "stub"),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "similar_incidents": [],
            "runbook_chunks": [],
            "errors": [{"node": "search_incident_history", "error": str(exc)}],
            **_trace("search_incident_history", t0, "error", error=str(exc)),
        }


# --------------------------------------------------------------------------
# assess_risk — [STUB Fase 3, motor completo na Fase 6 / feature/risk-engine]
# Versão simplificada da regra aditiva do PLAN.md §4, sem tendência/anomalia
# (isso entra com app/risk/anomaly.py). Já é 100% determinística e não olha
# nenhum campo do LLM além de `category` — a separação LLM-vs-regra que a
# Fase 6 testa explicitamente já vale a partir daqui.
# --------------------------------------------------------------------------


def _stub_risk_score(state: IncidentState) -> int:
    score = 0
    if state.get("environment") == "production":
        score += 2
    status = (state.get("service_status") or {}).get("status")
    if status == "down":
        score += 3
    return score


def _stub_severity(score: int) -> str:
    if score >= 6:
        return "high"
    if score >= 3:
        return "medium"
    return "low"


async def assess_risk(state: IncidentState) -> dict:
    t0 = time.perf_counter()
    score = _stub_risk_score(state)
    severity = _stub_severity(score)
    return {
        "risk_score": score,
        "severity": severity,
        "failure_risk": min(0.99, score / 10),
        "trend": "stable",
        "trend_confidence": 0.0,
        **_trace("assess_risk", t0, "stub", risk_score=score, severity=severity),
    }


# --------------------------------------------------------------------------
# approval_check — [STUB Fase 3, política completa na Fase 7 / feature/security]
# --------------------------------------------------------------------------

_MUTATING_KEYWORDS = ("restart", "delete", "drop", "kill", "rollback", "scale")


async def approval_check(state: IncidentState) -> dict:
    t0 = time.perf_counter()
    text = " ".join(state.get("key_signals", []) + [state.get("probable_cause", "")]).lower()
    looks_mutating = any(kw in text for kw in _MUTATING_KEYWORDS)
    severity = state.get("severity", "low")
    requires_approval = bool(
        state.get("llm_parse_failed")
        or (looks_mutating and state.get("environment") == "production")
        or severity in ("high", "critical")
        and state.get("environment") == "production"
    )
    action_class = "CHANGE" if looks_mutating else "RECOMMEND"
    return {
        "action_class": action_class,
        "requires_human_approval": requires_approval,
        **_trace("approval_check", t0, "stub", requires_human_approval=requires_approval),
    }


# --------------------------------------------------------------------------
# generate_recommendation — real (LLM configurável)
# --------------------------------------------------------------------------


async def generate_recommendation(state: IncidentState) -> dict:
    t0 = time.perf_counter()
    client = get_llm()
    prompt = build_recommendation_prompt(
        service=state["service"],
        environment=state["environment"],
        category=state.get("category", "unknown"),
        probable_cause=state.get("probable_cause", ""),
        similar_incidents=state.get("similar_incidents", []),
        runbook_chunks=state.get("runbook_chunks", []),
        service_status=state.get("service_status"),
    )
    result, degraded = await structured_with_fallback(client, RecommendationOut, prompt)

    if degraded or result is None:
        actions = default_actions_for_category(state.get("category", "unknown"))
        return {
            "summary": "Recomendação automática indisponível; ações padrão para a categoria.",
            "recommended_actions": actions,
            "terminal_reason": "completed_degraded",
            "tools_used": ["llm:recommend"],
            "errors": [
                {"node": "generate_recommendation", "error": "llm_structured_output_failed"}
            ],
            **_trace("generate_recommendation", t0, "degraded"),
        }

    return {
        "summary": result.summary,
        "recommended_actions": result.recommended_actions,
        "terminal_reason": "completed",
        "tools_used": ["llm:recommend"],
        **_trace("generate_recommendation", t0, "ok"),
    }


# --------------------------------------------------------------------------
# finalize_* — garantem que TODO caminho terminal produz um state completo
# o bastante para virar IncidentResponse (app/api/routes.py nunca precisa
# tratar state parcial por caso).
# --------------------------------------------------------------------------

_DEFAULTS = {
    "category": "unknown",
    "probable_cause": "",
    "confidence": 0.0,
    "recommended_actions": [],
    "severity": "low",
    "risk_score": 0,
    "failure_risk": 0.0,
    "trend": "stable",
    "trend_confidence": 0.0,
    "action_class": "READ",
    "requires_human_approval": False,
}


async def finalize_blocked(state: IncidentState) -> dict:
    t0 = time.perf_counter()
    if not state.get("is_valid", True):
        reason = "invalid_input"
    elif state.get("security_violation"):
        reason = "security_blocked"
    else:
        reason = "blocked"
    update: dict[str, Any] = {"terminal_reason": reason}
    for key, default in _DEFAULTS.items():
        if state.get(key) is None:
            update[key] = default
    update.update(_trace("finalize_blocked", t0, "ok", reason=reason))
    return update


async def finalize_pending_approval(state: IncidentState) -> dict:
    t0 = time.perf_counter()
    update: dict[str, Any] = {
        "terminal_reason": "pending_approval",
        "requires_human_approval": True,
    }
    for key, default in _DEFAULTS.items():
        if state.get(key) is None:
            update[key] = default
    update.update(_trace("finalize_pending_approval", t0, "ok"))
    return update
