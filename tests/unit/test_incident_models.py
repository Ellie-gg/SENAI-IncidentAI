from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models.incident import MAX_LOGS, IncidentRequest
from app.models.response import EvidenceBlock, IncidentResponse, RiskBlock


def _valid_payload(**overrides) -> dict:
    payload = {
        "service": "payments-api",
        "environment": "production",
        "description": "API presenting database connection errors",
        "logs": ["ERROR database connection timeout", "ERROR connection pool exhausted"],
    }
    payload.update(overrides)
    return payload


def test_valid_payload_parses():
    req = IncidentRequest(**_valid_payload())
    assert req.service == "payments-api"
    assert req.environment == "production"
    assert len(req.logs) == 2


def test_logs_can_be_empty():
    req = IncidentRequest(**_valid_payload(logs=[]))
    assert req.logs == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"service": ""},
        {"service": "   "},
        {"description": ""},
        {"description": "   "},
        {"environment": "prod"},  # não é um dos Literal aceitos
        {"logs": ["x"] * (MAX_LOGS + 1)},  # payload grande demais
    ],
)
def test_invalid_payload_raises(overrides):
    with pytest.raises(ValidationError):
        IncidentRequest(**_valid_payload(**overrides))


def test_long_log_line_is_truncated_not_rejected():
    huge_line = "E" * 10_000
    req = IncidentRequest(**_valid_payload(logs=[huge_line]))
    assert len(req.logs[0]) <= 2000


def test_description_too_long_is_rejected():
    with pytest.raises(ValidationError):
        IncidentRequest(**_valid_payload(description="x" * 5000))


def test_incident_response_requires_all_blocks():
    resp = IncidentResponse(
        incident_id="INC-1",
        trace_id="trace-1",
        category="database_connectivity",
        severity="high",
        probable_cause="Connection pool exhaustion",
        confidence=0.88,
        recommended_actions=["Check database availability"],
        risk=RiskBlock(score=8, failure_risk=0.71, trend="increasing", trend_confidence=0.8),
        action_class="RECOMMEND",
        requires_human_approval=False,
        evidence=EvidenceBlock(service_status="degraded", monitoring_source="monitoring"),
    )
    assert resp.degraded is False
    assert resp.risk.trend == "increasing"


def test_incident_response_rejects_out_of_range_confidence():
    with pytest.raises(ValidationError):
        IncidentResponse(
            incident_id="INC-1",
            trace_id="trace-1",
            category="unknown",
            severity="low",
            probable_cause="x",
            confidence=1.5,  # fora de [0, 1]
            risk=RiskBlock(score=0, failure_risk=0.0, trend="stable", trend_confidence=0.0),
            action_class="READ",
            requires_human_approval=False,
            evidence=EvidenceBlock(),
        )
