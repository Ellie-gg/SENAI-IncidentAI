"""Detecção de tendência e estimativa de risco de falha — puro, sem I/O,
sem LLM. Não usa numpy (regressão linear em ≤50 pontos é mais barata à mão
que a dependência).

`classify_trend` é o módulo que classifica a série `[0.05, 0.09, 0.14]` do
enunciado como "increasing" (`rel_slope ≈ 0.48`, bem acima do limiar de
0.10) — ver tests/unit/test_anomaly.py para o cálculo conferido a mão.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

TrendLabel = Literal["increasing", "stable", "decreasing"]
FailureRiskLabel = Literal["low", "medium", "high", "critical"]

_EPS = 1e-6


@dataclass(frozen=True)
class TrendResult:
    slope: float  # unidades de error_rate por amostra
    rel_slope: float  # slope / max(mean, EPS) — adimensional, comparável entre séries
    ewma: float  # nível "atual" suavizado (EWMA), menos sensível a 1 pico isolado
    label: TrendLabel
    n: int
    confidence: float  # 0..1 — cresce com n e |rel_slope|; 0 quando n < min_points


def linreg_slope(values: Sequence[float]) -> float:
    """Inclinação de uma regressão linear simples (OLS) sobre `values`,
    tratando o índice (0, 1, 2, ...) como eixo x."""
    n = len(values)
    if n < 2:
        return 0.0
    x_mean = (n - 1) / 2
    y_mean = sum(values) / n
    numerator = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    denominator = sum((i - x_mean) ** 2 for i in range(n))
    if denominator == 0:
        return 0.0
    return numerator / denominator


def ewma(values: Sequence[float], alpha: float = 0.3) -> float:
    if not values:
        return 0.0
    estimate = values[0]
    for v in values[1:]:
        estimate = alpha * v + (1 - alpha) * estimate
    return estimate


def classify_trend(
    values: Sequence[float],
    *,
    alpha: float = 0.3,
    rel_threshold: float = 0.10,
    min_points: int = 3,
) -> TrendResult:
    n = len(values)
    if n < min_points:
        # Dados insuficientes para afirmar uma tendência — "stable" com
        # confiança 0 é honesto; não é o mesmo que "confirmadamente estável".
        return TrendResult(
            slope=0.0, rel_slope=0.0, ewma=ewma(values, alpha), label="stable", n=n, confidence=0.0
        )

    slope = linreg_slope(values)
    mean = sum(values) / n
    rel_slope = slope / max(mean, _EPS)
    smoothed = ewma(values, alpha)

    variance = sum((v - mean) ** 2 for v in values) / n
    stdev = math.sqrt(variance)
    is_noisy = (stdev / max(mean, _EPS) > 0.8) and (abs(rel_slope) < 0.25)

    if is_noisy:
        label: TrendLabel = "stable"
    elif rel_slope > rel_threshold:
        label = "increasing"
    elif rel_slope < -rel_threshold:
        label = "decreasing"
    else:
        label = "stable"

    # Confiança cresce com o tamanho da série e com a magnitude relativa da
    # inclinação — poucos pontos ou inclinação perto do limiar => baixa confiança.
    magnitude_factor = min(1.0, abs(rel_slope) / rel_threshold) if rel_threshold else 0.0
    size_factor = min(1.0, n / 10)
    confidence = round(magnitude_factor * size_factor, 3)

    return TrendResult(
        slope=slope, rel_slope=rel_slope, ewma=smoothed, label=label, n=n, confidence=confidence
    )


_STATUS_WEIGHT = {"down": 2.5, "degraded": 1.2, "up": 0.0, "unknown": 0.4}
_ENVIRONMENT_WEIGHT = {"production": 0.5, "staging": 0.1, "development": 0.0}


def failure_risk(
    *,
    trend: TrendResult,
    current_error_rate: float,
    latency_p95_ms: float,
    status: str,
    environment: str,
) -> float:
    """Probabilidade estimada de falha — logística limitada sobre
    features interpretáveis (não um modelo treinado; os coeficientes são
    documentados aqui e fixados em RiskConfig-equivalente via testes).

    Monitoramento indisponível (`status="unknown"`) usa um peso brando
    (0.4) — a intenção é que um monitor fora do ar NÃO fabrique um risco
    alto sozinho; ele deve empurrar para revisão humana (app/security),
    não para uma classificação de risco inflada por falta de dado.
    """
    level = trend.ewma if trend.n > 0 else current_error_rate
    z = -3.2
    z += 6.0 * min(level, 0.5) / 0.5
    z += 2.0 * max(0.0, min(trend.rel_slope, 1.0))
    z += 1.2 * min(latency_p95_ms, 5000.0) / 5000.0
    z += _STATUS_WEIGHT.get(status, 0.4)
    z += _ENVIRONMENT_WEIGHT.get(environment, 0.0)

    p = 1 / (1 + math.exp(-z))
    return round(min(max(p, 0.01), 0.99), 3)


def classify_failure_risk(p: float) -> FailureRiskLabel:
    if p < 0.25:
        return "low"
    if p < 0.50:
        return "medium"
    if p < 0.75:
        return "high"
    return "critical"
