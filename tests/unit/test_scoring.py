from __future__ import annotations

import pytest

from app.risk.scoring import DEFAULT_RISK_CONFIG, classify_severity, compute_risk_score


def _score(**overrides) -> int:
    params = {
        "environment": "development",
        "error_rate": 0.0,
        "latency_p95_ms": 0.0,
        "status": "up",
        "trend_label": "stable",
    }
    params.update(overrides)
    return compute_risk_score(**params)


def test_healthy_service_scores_zero():
    assert _score() == 0


def test_production_adds_weight():
    assert _score(environment="production") == DEFAULT_RISK_CONFIG.production_weight


def test_high_error_rate_adds_weight():
    assert _score(error_rate=0.5) == DEFAULT_RISK_CONFIG.error_rate_weight


def test_error_rate_at_threshold_does_not_count():
    # regra é > threshold, não >=
    assert _score(error_rate=DEFAULT_RISK_CONFIG.error_rate_threshold) == 0


def test_high_latency_adds_weight():
    assert _score(latency_p95_ms=5000) == DEFAULT_RISK_CONFIG.latency_weight


def test_status_down_adds_weight():
    assert _score(status="down") == DEFAULT_RISK_CONFIG.status_down_weight


def test_increasing_trend_adds_weight():
    assert _score(trend_label="increasing") == DEFAULT_RISK_CONFIG.trend_increasing_weight


def test_canonical_high_severity_case_from_enunciado():
    # production + error_rate>0.10 + latency>2000ms + increasing trend
    score = _score(
        environment="production", error_rate=0.19, latency_p95_ms=2350, trend_label="increasing"
    )
    assert score == (
        DEFAULT_RISK_CONFIG.production_weight
        + DEFAULT_RISK_CONFIG.error_rate_weight
        + DEFAULT_RISK_CONFIG.latency_weight
        + DEFAULT_RISK_CONFIG.trend_increasing_weight
    )
    assert classify_severity(score) == "high"


def test_everything_wrong_at_once_is_critical():
    score = _score(
        environment="production",
        error_rate=0.99,
        latency_p95_ms=9999,
        status="down",
        trend_label="increasing",
    )
    assert classify_severity(score) == "critical"


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (0, "low"),
        (2, "low"),
        (3, "medium"),
        (5, "medium"),
        (6, "high"),
        (8, "high"),
        (9, "critical"),
        (15, "critical"),
    ],
)
def test_classify_severity_boundaries(score, expected):
    assert classify_severity(score) == expected
