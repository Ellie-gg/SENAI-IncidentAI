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

import time
from typing import Any

from app.agent.prompts import build_analysis_prompt, build_recommendation_prompt
from app.agent.state import IncidentState
from app.config import get_settings
from app.models.llm_io import AnalysisOut, RecommendationOut
from app.risk.anomaly import classify_trend, failure_risk
from app.risk.scoring import classify_severity, compute_risk_score
from app.services.llm import default_actions_for_category, get_llm, structured_with_fallback
from app.tools.registry import call_tool


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
# check_service_status — real (Fase 4 / feature/tool-integration)
# Roda em paralelo com search_incident_history (fan-out a partir de
# analyze_incident). call_tool() é async e não-bloqueante (httpx.AsyncClient
# com timeout/retry/fallback em app/tools/monitoring_client.py).
# --------------------------------------------------------------------------


async def check_service_status(state: IncidentState) -> dict:
    t0 = time.perf_counter()
    try:
        status = await call_tool(
            "get_service_status", service=state["service"], environment=state["environment"]
        )
        history = status.get("history", [])
        return {
            "service_status": status,
            "error_rate_series": [p["error_rate"] for p in history],
            "latency_series": [p["latency_p95_ms"] for p in history],
            "tools_used": ["tool:check_service_status"],
            **_trace("check_service_status", t0, status.get("source", "unknown")),
        }
    except Exception as exc:  # noqa: BLE001 — nó paralelo nunca propaga exceção
        return {
            "service_status": None,
            "error_rate_series": [],
            "latency_series": [],
            "errors": [{"node": "check_service_status", "error": str(exc)}],
            **_trace("check_service_status", t0, "error", error=str(exc)),
        }


# --------------------------------------------------------------------------
# search_incident_history — [STUB Fase 4, real na Fase 5 / feature/memory-rag]
# Roda em paralelo com check_service_status. call_tool() já é a mesma porta
# de entrada usada pela tool real (app/tools/core.py); a Fase 5 troca só o
# corpo de tool_search_incident_history/tool_search_runbooks (FTS5, via
# asyncio.to_thread para não bloquear o event loop) — este nó não muda.
# --------------------------------------------------------------------------


async def search_incident_history(state: IncidentState) -> dict:
    t0 = time.perf_counter()
    try:
        history = await call_tool(
            "search_incident_history", query=state["description"], service=state["service"]
        )
        runbooks = await call_tool("search_runbooks", query=state["description"])
        return {
            "similar_incidents": history.get("similar_incidents", []),
            "runbook_chunks": runbooks.get("runbook_chunks", []),
            "tools_used": ["memory:search_incident_history", "memory:search_runbooks"],
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
# assess_risk — real (Fase 6 / feature/risk-engine)
# 100% determinística: só lê environment, métricas de monitoramento e a
# tendência calculada por app/risk/anomaly.py — nenhum campo do LLM
# (category, probable_cause, confidence) entra aqui. É a separação
# LLM-vs-regra que tests/unit/test_scoring.py testa explicitamente.
# --------------------------------------------------------------------------


async def assess_risk(state: IncidentState) -> dict:
    t0 = time.perf_counter()
    status_info = state.get("service_status") or {}
    status = status_info.get("status", "unknown")
    error_series = state.get("error_rate_series") or []
    latency_series = state.get("latency_series") or []

    current_error_rate = status_info.get("error_rate", error_series[-1] if error_series else 0.0)
    current_latency = status_info.get(
        "latency_p95_ms", latency_series[-1] if latency_series else 0.0
    )

    trend = classify_trend(error_series)
    risk_prob = failure_risk(
        trend=trend,
        current_error_rate=current_error_rate,
        latency_p95_ms=current_latency,
        status=status,
        environment=state["environment"],
    )
    score = compute_risk_score(
        environment=state["environment"],
        error_rate=current_error_rate,
        latency_p95_ms=current_latency,
        status=status,
        trend_label=trend.label,
    )
    severity = classify_severity(score)

    return {
        "risk_score": score,
        "severity": severity,
        "failure_risk": risk_prob,
        "trend": trend.label,
        "trend_confidence": trend.confidence,
        **_trace("assess_risk", t0, "ok", risk_score=score, severity=severity, trend=trend.label),
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
