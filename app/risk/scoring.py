"""Severidade determinística — regra aditiva do PLAN.md §4, mais o bônus
de tendência (Fase 6). Todos os limiares/pesos moram em `RiskConfig` para
os testes fixarem os valores exatos e para tuning futuro ficar em um único
lugar.

Regra que a Fase 6 existe para provar: nada aqui lê `category`,
`probable_cause` ou `confidence` (campos do LLM) — só `environment`,
métricas de monitoramento e `trend.label` (calculado por
`app/risk/anomaly.py`). Ver tests/unit/test_scoring.py para o teste que
mutar campos do LLM não muda severidade/score.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Severity = Literal["low", "medium", "high", "critical"]


@dataclass(frozen=True)
class RiskConfig:
    production_weight: int = 2
    error_rate_threshold: float = 0.10
    error_rate_weight: int = 3
    latency_threshold_ms: float = 2000.0
    latency_weight: int = 2
    status_down_weight: int = 3
    trend_increasing_weight: int = 1

    medium_from: int = 3
    high_from: int = 6
    critical_from: int = 9


DEFAULT_RISK_CONFIG = RiskConfig()


def compute_risk_score(
    *,
    environment: str,
    error_rate: float,
    latency_p95_ms: float,
    status: str,
    trend_label: str,
    config: RiskConfig = DEFAULT_RISK_CONFIG,
) -> int:
    score = 0
    if environment == "production":
        score += config.production_weight
    if error_rate > config.error_rate_threshold:
        score += config.error_rate_weight
    if latency_p95_ms > config.latency_threshold_ms:
        score += config.latency_weight
    if status == "down":
        score += config.status_down_weight
    if trend_label == "increasing":
        score += config.trend_increasing_weight
    return score


def classify_severity(score: int, config: RiskConfig = DEFAULT_RISK_CONFIG) -> Severity:
    if score >= config.critical_from:
        return "critical"
    if score >= config.high_from:
        return "high"
    if score >= config.medium_from:
        return "medium"
    return "low"
