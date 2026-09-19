from __future__ import annotations

from app.agent.routing import (
    route_after_approval,
    route_after_risk,
    route_after_security,
    route_after_validate,
)


def test_route_after_validate_ok():
    assert route_after_validate({"is_valid": True}) == "ok"


def test_route_after_validate_invalid():
    assert route_after_validate({"is_valid": False}) == "invalid"
    assert route_after_validate({}) == "invalid"  # ausência de is_valid == inválido


def test_route_after_security_block():
    assert route_after_security({"security_violation": True}) == "block"


def test_route_after_security_continue():
    assert route_after_security({"security_violation": False}) == "continue"
    assert route_after_security({}) == "continue"


def test_route_after_risk_retry_while_under_max_iterations():
    state = {"needs_reanalysis": True, "iteration_count": 1}
    assert route_after_risk(state) == "retry"


def test_route_after_risk_stops_at_max_iterations():
    # default MAX_ITERATIONS=3 (app/config.py) — no limite, não deve mais tentar retry
    state = {"needs_reanalysis": True, "iteration_count": 3}
    assert route_after_risk(state) == "recommend"


def test_route_after_risk_recommend_when_nothing_pending():
    state = {"needs_reanalysis": False, "iteration_count": 1}
    assert route_after_risk(state) == "recommend"


def test_route_after_approval_needs_approval():
    assert route_after_approval({"requires_human_approval": True}) == "needs_approval"


def test_route_after_approval_auto():
    assert route_after_approval({"requires_human_approval": False}) == "auto"
    assert route_after_approval({}) == "auto"
