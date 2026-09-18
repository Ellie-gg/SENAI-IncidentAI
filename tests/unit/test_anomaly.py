from __future__ import annotations

import pytest

from app.risk.anomaly import classify_failure_risk, classify_trend, ewma, failure_risk, linreg_slope

# --------------------------------------------------------------------------
# linreg_slope / ewma — primitivas
# --------------------------------------------------------------------------


def test_linreg_slope_of_flat_series_is_zero():
    assert linreg_slope([0.1, 0.1, 0.1, 0.1]) == pytest.approx(0.0)


def test_linreg_slope_of_perfectly_increasing_series():
    assert linreg_slope([1.0, 2.0, 3.0, 4.0]) == pytest.approx(1.0)


def test_linreg_slope_single_point_is_zero():
    assert linreg_slope([5.0]) == 0.0


def test_linreg_slope_empty_is_zero():
    assert linreg_slope([]) == 0.0


def test_ewma_of_empty_is_zero():
    assert ewma([]) == 0.0


def test_ewma_weights_recent_values_more():
    # série com um salto no final -> EWMA deve ficar mais perto do fim que a média simples
    values = [0.1, 0.1, 0.1, 0.5]
    e = ewma(values, alpha=0.3)
    simple_mean = sum(values) / len(values)
    assert e > simple_mean


# --------------------------------------------------------------------------
# classify_trend — o caso canônico do enunciado e as bordas
# --------------------------------------------------------------------------


def test_classify_trend_canonical_increasing_case_from_enunciado():
    # [0.05, 0.09, 0.14] -> slope=0.045, mean=0.0933, rel_slope≈0.482 -> increasing
    result = classify_trend([0.05, 0.09, 0.14])
    assert result.label == "increasing"
    assert result.rel_slope == pytest.approx(0.482, abs=0.01)
    assert result.confidence > 0.0


def test_classify_trend_flat_series_is_stable():
    result = classify_trend([0.01, 0.01, 0.01, 0.01, 0.01])
    assert result.label == "stable"


def test_classify_trend_decreasing_series():
    result = classify_trend([0.30, 0.20, 0.10])
    assert result.label == "decreasing"
    assert result.rel_slope < 0


def test_classify_trend_insufficient_points_is_stable_with_zero_confidence():
    result = classify_trend([0.05, 0.09])  # n=2 < min_points=3
    assert result.label == "stable"
    assert result.confidence == 0.0
    assert result.n == 2


def test_classify_trend_empty_series():
    result = classify_trend([])
    assert result.label == "stable"
    assert result.confidence == 0.0


def test_classify_trend_noisy_series_downgrades_to_stable():
    # alta variância relativa, inclinação fraca -> não deve virar "increasing" por ruído
    noisy = [0.01, 0.20, 0.02, 0.18, 0.03]
    result = classify_trend(noisy)
    assert result.label == "stable"


def test_classify_trend_confidence_grows_with_more_points_same_shape():
    short = classify_trend([0.05, 0.09, 0.14])
    long = classify_trend([0.05, 0.07, 0.09, 0.11, 0.13, 0.14, 0.16, 0.18, 0.20, 0.22])
    assert long.confidence >= short.confidence


# --------------------------------------------------------------------------
# failure_risk — bandas e o caso "monitoramento indisponível não infla risco"
# --------------------------------------------------------------------------


def test_failure_risk_is_bounded_between_001_and_099():
    trend = classify_trend([0.9, 0.95, 0.99])
    p = failure_risk(
        trend=trend,
        current_error_rate=0.99,
        latency_p95_ms=9999,
        status="down",
        environment="production",
    )
    assert 0.01 <= p <= 0.99


def test_failure_risk_low_for_healthy_service():
    trend = classify_trend([0.01, 0.01, 0.01])
    p = failure_risk(
        trend=trend,
        current_error_rate=0.01,
        latency_p95_ms=100,
        status="up",
        environment="production",
    )
    assert classify_failure_risk(p) == "low"


def test_failure_risk_high_for_down_service_with_increasing_errors():
    trend = classify_trend([0.05, 0.09, 0.14, 0.19])
    p = failure_risk(
        trend=trend,
        current_error_rate=0.19,
        latency_p95_ms=2350,
        status="down",
        environment="production",
    )
    assert classify_failure_risk(p) in ("high", "critical")


def test_failure_risk_unknown_status_does_not_inflate_risk_like_down():
    """Monitoramento indisponível (status=unknown) não pode produzir um
    risco tão alto quanto um serviço confirmadamente down — a intenção é
    empurrar para revisão humana (segurança), não fabricar um risco alto
    a partir da ausência de dado."""
    trend = classify_trend([0.0, 0.0, 0.0])
    p_unknown = failure_risk(
        trend=trend,
        current_error_rate=0.0,
        latency_p95_ms=100,
        status="unknown",
        environment="production",
    )
    p_down = failure_risk(
        trend=trend,
        current_error_rate=0.0,
        latency_p95_ms=100,
        status="down",
        environment="production",
    )
    assert p_unknown < p_down


@pytest.mark.parametrize(
    ("p", "expected"),
    [
        (0.1, "low"),
        (0.24, "low"),
        (0.25, "medium"),
        (0.49, "medium"),
        (0.5, "high"),
        (0.74, "high"),
        (0.75, "critical"),
        (0.9, "critical"),
    ],
)
def test_classify_failure_risk_boundaries(p, expected):
    assert classify_failure_risk(p) == expected
