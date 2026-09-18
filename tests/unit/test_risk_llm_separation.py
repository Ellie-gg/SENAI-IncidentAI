"""A tese central do projeto: LLM decide categoria/causa/redação; regra
decide severidade/risco/aprovação. Este teste muta SÓ os campos que vêm do
LLM e confirma que assess_risk produz exatamente o mesmo resultado —
prova de que nenhum desses campos é lido pela regra de risco.
"""

from __future__ import annotations

from app.agent.nodes import assess_risk


def _base_state(**overrides) -> dict:
    state = {
        "environment": "production",
        "service_status": {"status": "degraded", "error_rate": 0.14, "latency_p95_ms": 1600.0},
        "error_rate_series": [0.03, 0.05, 0.09, 0.14],
        "latency_series": [400.0, 550.0, 900.0, 1600.0],
        "category": "database_connectivity",
        "probable_cause": "Connection pool exhaustion",
        "confidence": 0.85,
    }
    state.update(overrides)
    return state


async def test_mutating_llm_fields_does_not_change_risk_output():
    result_a = await assess_risk(_base_state())
    result_b = await assess_risk(
        _base_state(
            category="unknown",
            probable_cause="A completely different, unrelated made-up story",
            confidence=0.05,
        )
    )

    for key in ("risk_score", "severity", "failure_risk", "trend", "trend_confidence"):
        assert result_a[key] == result_b[key], f"{key} mudou só por causa de um campo do LLM"


async def test_changing_a_rule_input_does_change_risk_output():
    """Contraste com o teste acima: mudar um campo de REGRA (environment)
    tem que mudar o resultado — prova que o teste anterior não está
    passando por acidente (ex.: a função sempre devolver o mesmo valor)."""
    result_prod = await assess_risk(_base_state(environment="production"))
    result_dev = await assess_risk(_base_state(environment="development"))

    assert result_prod["risk_score"] != result_dev["risk_score"]
