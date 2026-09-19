"""Métricas em memória — terceiro sinal de observabilidade, além de logs
estruturados e auditoria. `GET /metrics` expõe um snapshot; não persiste
entre restarts (não é o objetivo: é o sinal que `scripts/anomaly_report.py`
usa, na Fase 10, para detectar anomalia/tendência operacional).
"""

from __future__ import annotations

import statistics
import threading
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class _NodeStats:
    count: int = 0
    error_count: int = 0
    durations_ms: list[float] = field(default_factory=list)


class MetricsRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._nodes: dict[str, _NodeStats] = defaultdict(_NodeStats)
        self._executions_total = 0
        self._fallback_total = 0
        self._blocked_total = 0
        self._pending_approval_total = 0

    def record_node(self, *, node: str, status: str, duration_ms: float) -> None:
        with self._lock:
            stats = self._nodes[node]
            stats.count += 1
            stats.durations_ms.append(duration_ms)
            if status == "error":
                stats.error_count += 1

    def record_execution(self, *, terminal_reason: str | None, degraded: bool) -> None:
        with self._lock:
            self._executions_total += 1
            if degraded:
                self._fallback_total += 1
            if terminal_reason == "security_blocked":
                self._blocked_total += 1
            if terminal_reason == "pending_approval":
                self._pending_approval_total += 1

    def snapshot(self) -> dict:
        with self._lock:
            nodes: dict[str, dict] = {}
            for name, stats in self._nodes.items():
                durations = sorted(stats.durations_ms)
                p95_index = max(0, int(len(durations) * 0.95) - 1)
                nodes[name] = {
                    "count": stats.count,
                    "error_count": stats.error_count,
                    "avg_duration_ms": round(statistics.fmean(durations), 2) if durations else 0.0,
                    "p95_duration_ms": round(durations[p95_index], 2) if durations else 0.0,
                }
            fallback_rate = (
                round(self._fallback_total / self._executions_total, 4)
                if self._executions_total
                else 0.0
            )
            return {
                "executions_total": self._executions_total,
                "fallback_total": self._fallback_total,
                "blocked_total": self._blocked_total,
                "pending_approval_total": self._pending_approval_total,
                "fallback_rate": fallback_rate,
                "nodes": nodes,
            }

    def reset(self) -> None:
        """Só para testes — não é exposta em nenhuma rota."""
        with self._lock:
            self._nodes.clear()
            self._executions_total = 0
            self._fallback_total = 0
            self._blocked_total = 0
            self._pending_approval_total = 0


_registry = MetricsRegistry()


def get_registry() -> MetricsRegistry:
    return _registry
