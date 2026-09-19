from __future__ import annotations

from app.observability.metrics import MetricsRegistry


def test_record_node_and_snapshot():
    registry = MetricsRegistry()
    registry.record_node(node="analyze_incident", status="ok", duration_ms=10.0)
    registry.record_node(node="analyze_incident", status="ok", duration_ms=20.0)
    registry.record_node(node="analyze_incident", status="error", duration_ms=5.0)

    snap = registry.snapshot()
    node = snap["nodes"]["analyze_incident"]
    assert node["count"] == 3
    assert node["error_count"] == 1
    assert node["avg_duration_ms"] == round((10.0 + 20.0 + 5.0) / 3, 2)


def test_p95_duration_uses_sorted_values():
    registry = MetricsRegistry()
    for d in [10, 20, 30, 40, 100]:
        registry.record_node(node="x", status="ok", duration_ms=float(d))
    snap = registry.snapshot()
    # sorted=[10,20,30,40,100], index=max(0, int(5*0.95)-1)=3 -> 40.0
    assert snap["nodes"]["x"]["p95_duration_ms"] == 40.0


def test_record_execution_counts_fallback_and_blocked():
    registry = MetricsRegistry()
    registry.record_execution(terminal_reason="completed", degraded=False)
    registry.record_execution(terminal_reason="completed_degraded", degraded=True)
    registry.record_execution(terminal_reason="security_blocked", degraded=False)
    registry.record_execution(terminal_reason="pending_approval", degraded=False)

    snap = registry.snapshot()
    assert snap["executions_total"] == 4
    assert snap["fallback_total"] == 1
    assert snap["blocked_total"] == 1
    assert snap["pending_approval_total"] == 1
    assert snap["fallback_rate"] == round(1 / 4, 4)


def test_snapshot_with_no_executions_does_not_divide_by_zero():
    registry = MetricsRegistry()
    snap = registry.snapshot()
    assert snap["executions_total"] == 0
    assert snap["fallback_rate"] == 0.0


def test_reset_clears_all_state():
    registry = MetricsRegistry()
    registry.record_node(node="x", status="ok", duration_ms=1.0)
    registry.record_execution(terminal_reason="completed", degraded=False)
    registry.reset()
    snap = registry.snapshot()
    assert snap["executions_total"] == 0
    assert snap["nodes"] == {}
