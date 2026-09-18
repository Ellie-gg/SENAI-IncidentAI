"""Testes de integração do grafo compilado — sem subir a API, sem chamar
LLM externo (LLM_PROVIDER=mock via tests/conftest.py).
"""

from __future__ import annotations

import asyncio
import operator
import time
from typing import Annotated, TypedDict

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.errors import InvalidUpdateError
from langgraph.graph import END, START, StateGraph

from app.agent.graph import build_graph
from app.agent.state import initial_state


def _run(**overrides):
    graph = build_graph(checkpointer=MemorySaver())
    state = initial_state(
        incident_id=overrides.pop("incident_id", "INC-TEST"),
        trace_id="trace-test",
        service=overrides.pop("service", "payments-api"),
        environment=overrides.pop("environment", "production"),
        description=overrides.pop("description", "API presenting database connection errors"),
        logs=overrides.pop("logs", ["ERROR database connection timeout"]),
    )
    config = {"configurable": {"thread_id": state["incident_id"]}, "recursion_limit": 25}
    return graph, state, config


async def test_happy_path_end_to_end_reaches_generate_recommendation():
    graph, state, config = _run()
    final = await graph.ainvoke(state, config=config)

    assert final["terminal_reason"] in ("completed", "completed_degraded")
    assert final["is_valid"] is True
    assert final["security_violation"] is False
    assert final["category"] == "database_connectivity"
    assert len(final["recommended_actions"]) >= 1
    # as duas branches paralelas escreveram e sobreviveram ao fan-in
    node_names = {n["node"] for n in final["node_trace"]}
    assert {"check_service_status", "search_incident_history", "assess_risk"} <= node_names


async def test_invalid_input_short_circuits_to_finalize_blocked():
    graph, state, config = _run(service="", description="x")
    final = await graph.ainvoke(state, config=config)

    assert final["is_valid"] is False
    assert final["terminal_reason"] == "invalid_input"
    # não deve ter chegado a analisar nada
    node_names = {n["node"] for n in final["node_trace"]}
    assert "analyze_incident" not in node_names


async def test_low_confidence_triggers_retry_loop_with_new_evidence():
    """Categoria não reconhecida -> confidence baixa -> needs_reanalysis=True
    -> route_after_approval devolve 'retry' -> analyze_incident roda de novo
    (iteration_count sobe para 2) antes de seguir para o resto do grafo."""
    graph, state, config = _run(
        description="Something unusual is happening, cause is unclear",
        logs=[],
        environment="staging",
    )
    final = await graph.ainvoke(state, config=config)

    assert final["iteration_count"] == 2
    analyze_calls = [n for n in final["node_trace"] if n["node"] == "analyze_incident"]
    assert len(analyze_calls) == 2


async def test_llm_total_failure_degrades_to_pending_approval_without_crashing(monkeypatch):
    """LLM_PROVIDER=mock_fail: a escada de fallback (structured_with_fallback)
    esgota todas as tentativas -> llm_parse_failed=True -> approval_check
    força aprovação humana. O grafo nunca propaga exceção pra API."""
    monkeypatch.setenv("LLM_PROVIDER", "mock_fail")
    from app.config import get_settings
    from app.services import llm as llm_module

    get_settings.cache_clear()
    llm_module.get_llm.cache_clear()
    try:
        graph, state, config = _run()
        final = await graph.ainvoke(state, config=config)

        assert final["llm_parse_failed"] is True
        assert final["requires_human_approval"] is True
        assert final["terminal_reason"] == "pending_approval"
    finally:
        get_settings.cache_clear()
        llm_module.get_llm.cache_clear()


async def test_max_iterations_caps_the_retry_loop():
    """Com LLM_PROVIDER=mock e descrição sem sinal nenhum, a 2a tentativa
    também terá confiança baixa — mas o loop não pode rodar indefinidamente:
    route_after_approval para em iteration_count == MAX_ITERATIONS (3)."""
    graph, state, config = _run(description="???", logs=[], environment="staging")
    final = await graph.ainvoke(state, config=config)

    assert final["iteration_count"] <= 3
    analyze_calls = [n for n in final["node_trace"] if n["node"] == "analyze_incident"]
    assert len(analyze_calls) <= 3


async def test_check_service_status_and_search_history_both_survive_fanin():
    """As duas branches paralelas realmente escrevem no state e sobrevivem
    ao fan-in em assess_risk (a prova de tempo de parede fica isolada em
    test_fanout_topology_runs_nodes_concurrently, abaixo — decorrelacionada
    da duração real de check_service_status/search_incident_history, que
    muda a cada fase conforme os stubs viram implementação real)."""
    graph, state, config = _run()
    final = await graph.ainvoke(state, config=config)

    trace_by_node = {n["node"]: n for n in final["node_trace"]}
    assert "check_service_status" in trace_by_node
    assert "search_incident_history" in trace_by_node
    assert final.get("service_status") is not None


# --------------------------------------------------------------------------
# Prova de paralelismo real isolada num grafo sintético mínimo (mesmo padrão
# do teste de regressão de reducer, abaixo): dois nós com sleep conhecido e
# igual, fan-out/fan-in idêntico ao do grafo de produção. Isolar do grafo de
# negócio evita que este teste fique flaky (ou pare de testar o que
# deveria) conforme check_service_status/search_incident_history deixam de
# ser stub — Fases 4 e 5 substituem os corpos, não a topologia.
# --------------------------------------------------------------------------


class _TimingState(TypedDict, total=False):
    node_trace: Annotated[list[dict], operator.add]


async def _slow_a(state: _TimingState) -> dict:
    await asyncio.sleep(0.1)
    return {"node_trace": [{"node": "a"}]}


async def _slow_b(state: _TimingState) -> dict:
    await asyncio.sleep(0.1)
    return {"node_trace": [{"node": "b"}]}


def _build_fanout_timing_graph():
    g = StateGraph(_TimingState)
    g.add_node("start", lambda state: {})
    g.add_node("a", _slow_a)
    g.add_node("b", _slow_b)
    g.add_node("join", lambda state: {})
    g.add_edge(START, "start")
    g.add_edge("start", "a")
    g.add_edge("start", "b")
    g.add_edge("a", "join")
    g.add_edge("b", "join")
    g.add_edge("join", END)
    return g.compile()


async def test_fanout_topology_runs_nodes_concurrently():
    graph = _build_fanout_timing_graph()
    t0 = time.perf_counter()
    final = await graph.ainvoke({})
    total_s = time.perf_counter() - t0

    assert {n["node"] for n in final["node_trace"]} == {"a", "b"}
    # serial seria >= 0.2s (0.1 + 0.1); paralelo fica perto de 0.1s — folga
    # generosa (0.17s) para não ficar flaky em CI lento.
    assert total_s < 0.17


# --------------------------------------------------------------------------
# Regressão: reducer ausente numa chave escrita por >1 nó DEVE quebrar alto
# e claro (InvalidUpdateError), não silenciosamente. Documenta a regra do
# app/agent/state.py para quem for adicionar um novo nó paralelo no futuro.
# --------------------------------------------------------------------------


class _BadState(TypedDict, total=False):
    shared_no_reducer: str  # escrita por 2 nós, SEM Annotated[..., reducer]
    ok_list: Annotated[list[str], operator.add]


async def _a(state: _BadState) -> dict:
    return {"shared_no_reducer": "from-a", "ok_list": ["a"]}


async def _b(state: _BadState) -> dict:
    return {"shared_no_reducer": "from-b", "ok_list": ["b"]}


async def _join(state: _BadState) -> dict:
    return {}


def _build_bad_fanout_graph():
    g = StateGraph(_BadState)
    g.add_node("start", lambda state: {})
    g.add_node("a", _a)
    g.add_node("b", _b)
    g.add_node("join", _join)
    g.add_edge(START, "start")
    g.add_edge("start", "a")
    g.add_edge("start", "b")
    g.add_edge("a", "join")
    g.add_edge("b", "join")
    g.add_edge("join", END)
    return g.compile()


async def test_missing_reducer_on_concurrent_write_raises_invalid_update_error():
    graph = _build_bad_fanout_graph()
    with pytest.raises(InvalidUpdateError):
        await graph.ainvoke({})
