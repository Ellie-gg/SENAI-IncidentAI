"""Testes dos scripts de DevOps inteligente (Fase 10). Cobrem a mecânica
determinística (parsing, cálculo de risco, escrita de arquivo) sem exigir
LLM real — LLM_PROVIDER=mock (default dos testes) é suficiente para
validar que os scripts funcionam ponta a ponta.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.ai_log_analysis import _parse_stage, analyze_stage
from scripts.anomaly_report import _is_anomalous, analyze_service


async def test_analyze_stage_returns_non_empty_text():
    result = await analyze_stage("lint", "ruff check .\nAll checks passed!")
    assert isinstance(result, str)
    assert len(result) > 0


async def test_analyze_stage_truncates_huge_logs():
    huge_log = "line\n" * 20_000  # bem acima de MAX_LOG_CHARS
    # não deve lançar exceção nem travar — só garante que o prompt final
    # (log truncado) ainda é processável
    result = await analyze_stage("test", huge_log)
    assert isinstance(result, str)


def test_parse_stage_splits_name_and_path():
    name, path = _parse_stage("lint=/tmp/lint.log")
    assert name == "lint"
    assert path == Path("/tmp/lint.log")


def test_parse_stage_rejects_missing_equals():
    import argparse

    import pytest

    with pytest.raises(argparse.ArgumentTypeError):
        _parse_stage("no-equals-sign-here")


async def test_analyze_service_computes_real_risk_for_degraded_increasing_scenario():
    scenario = {
        "status": "degraded",
        "error_rate_series": [0.03, 0.05, 0.09, 0.14, 0.19],
        "latency_series": [400.0, 550.0, 900.0, 1600.0, 2350.0],
    }
    result = await analyze_service("payments-api", scenario)

    assert result["trend"] == "increasing"
    assert result["severity"] in ("high", "critical")
    assert 0.0 <= result["failure_risk"] <= 1.0
    assert len(result["explanation"]) > 0


async def test_analyze_service_healthy_scenario_is_not_anomalous():
    scenario = {
        "status": "up",
        "error_rate_series": [0.01, 0.01, 0.01, 0.01],
        "latency_series": [100.0, 100.0, 100.0, 100.0],
    }
    result = await analyze_service("auth-api", scenario)
    assert result["trend"] == "stable"
    assert not _is_anomalous(result)


def test_is_anomalous_flags_increasing_trend():
    assert _is_anomalous({"trend": "increasing", "severity": "low"}) is True


def test_is_anomalous_flags_high_severity_even_if_stable():
    assert _is_anomalous({"trend": "stable", "severity": "high"}) is True


def test_is_anomalous_false_for_healthy():
    assert _is_anomalous({"trend": "stable", "severity": "low"}) is False
