"""Logging estruturado (JSON), correlacionado por `trace_id`/`incident_id`.

`log_execution` emite uma linha JSON por nó executado (a partir de
`node_trace`, já coletado por cada nó do grafo — ver app/agent/nodes.py)
mais uma linha-resumo por requisição — é a trilha que permite reconstruir
uma execução inteira com um `grep` pelo `trace_id` (ver
docs/evidencias/fase8-trace.json).

Também atualiza `app/observability/metrics.py` (terceiro sinal) e delega a
`app/observability/audit.py` (segundo sinal) — um único ponto de chamada
em app/api/routes.py depois de `graph.ainvoke()`.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

from app.observability import metrics as metrics_module


def configure_logging(*, level: str = "INFO") -> None:
    log_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=log_level)
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.PrintLoggerFactory(sys.stdout),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "incidentai") -> Any:
    return structlog.get_logger(name)


def log_execution(*, incident_id: str, trace_id: str, state: dict) -> None:
    logger = get_logger("incidentai.graph")
    registry = metrics_module.get_registry()

    for entry in state.get("node_trace", []):
        node = entry.get("node", "unknown")
        status = entry.get("status", "unknown")
        duration_ms = float(entry.get("duration_ms", 0.0))
        logger.info(
            "node.executed",
            trace_id=trace_id,
            incident_id=incident_id,
            node=node,
            status=status,
            duration_ms=duration_ms,
            **{k: v for k, v in entry.items() if k not in ("node", "status", "duration_ms")},
        )
        registry.record_node(node=node, status=status, duration_ms=duration_ms)

    for error in state.get("errors", []):
        logger.warning("node.error", trace_id=trace_id, incident_id=incident_id, **error)

    degraded = (
        bool(state.get("llm_parse_failed")) or state.get("terminal_reason") == "completed_degraded"
    )
    total_duration_ms = round(
        sum(float(n.get("duration_ms", 0.0)) for n in state.get("node_trace", [])), 2
    )

    logger.info(
        "incident.analyzed",
        trace_id=trace_id,
        incident_id=incident_id,
        service=state.get("service"),
        environment=state.get("environment"),
        category=state.get("category"),
        severity=state.get("severity"),
        terminal_reason=state.get("terminal_reason"),
        requires_human_approval=state.get("requires_human_approval"),
        security_violation=state.get("security_violation"),
        degraded=degraded,
        total_duration_ms=total_duration_ms,
    )
    registry.record_execution(terminal_reason=state.get("terminal_reason"), degraded=degraded)
