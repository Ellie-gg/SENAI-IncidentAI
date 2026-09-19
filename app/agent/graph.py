"""Monta e compila o grafo LangGraph.

Topologia (revisada na Fase 7 — ver docs/refinamento-prompt.md: o motivo
de approval_check rodar depois de generate_recommendation, não antes):

    START -> validate_input -(invalid)-> finalize_blocked -> END
                  |(ok)
            security_check -(block)-> finalize_blocked -> END
                  |(continue)
            analyze_incident
                  |
      +-----------+-----------+          <- FAN-OUT: 2 edges do mesmo nó,
      |                       |             mesmo superstep (paralelo real)
 check_service_status   search_incident_history
      |                       |
      +-----------+-----------+          <- FAN-IN: assess_risk só roda
                  |                         depois que AMBOS terminarem
            assess_risk
                  |
      +-----------+------------------+
 (retry, iteration_count<MAX)     (recommend)
      |                                 |
analyze_incident (loop)      generate_recommendation
                                         |
                                  approval_check
                                         |
                          +--------------+---------------+
                    (needs_approval)                   (auto)
                          |                               |
              finalize_pending_approval                  END
                          |
                         END

Ver app/agent/state.py para as regras de reducer que tornam o fan-out/fan-in
seguro (chaves escritas por >1 nó precisam de Annotated[..., reducer]).
"""

from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agent import nodes, routing
from app.agent.state import IncidentState


def build_graph(checkpointer: BaseCheckpointSaver | None = None) -> CompiledStateGraph:
    g: StateGraph = StateGraph(IncidentState)

    g.add_node("validate_input", nodes.validate_input)
    g.add_node("security_check", nodes.security_check)
    g.add_node("finalize_blocked", nodes.finalize_blocked)
    g.add_node("analyze_incident", nodes.analyze_incident)
    g.add_node("check_service_status", nodes.check_service_status)
    g.add_node("search_incident_history", nodes.search_incident_history)
    g.add_node("assess_risk", nodes.assess_risk)
    g.add_node("generate_recommendation", nodes.generate_recommendation)
    g.add_node("approval_check", nodes.approval_check)
    g.add_node("finalize_pending_approval", nodes.finalize_pending_approval)

    g.add_edge(START, "validate_input")
    g.add_conditional_edges(
        "validate_input",
        routing.route_after_validate,
        {"invalid": "finalize_blocked", "ok": "security_check"},
    )
    g.add_conditional_edges(  # condicional #1
        "security_check",
        routing.route_after_security,
        {"block": "finalize_blocked", "continue": "analyze_incident"},
    )
    g.add_edge("finalize_blocked", END)

    # ---- FAN-OUT: duas arestas a partir do mesmo nó = mesmo superstep ----
    g.add_edge("analyze_incident", "check_service_status")
    g.add_edge("analyze_incident", "search_incident_history")
    # ---- FAN-IN: assess_risk só dispara quando AMBAS terminarem ----
    g.add_edge("check_service_status", "assess_risk")
    g.add_edge("search_incident_history", "assess_risk")

    g.add_conditional_edges(  # condicional #2 + parada do loop de retry
        "assess_risk",
        routing.route_after_risk,
        {"retry": "analyze_incident", "recommend": "generate_recommendation"},
    )
    g.add_edge("generate_recommendation", "approval_check")
    g.add_conditional_edges(  # condicional #3
        "approval_check",
        routing.route_after_approval,
        {"needs_approval": "finalize_pending_approval", "auto": END},
    )
    g.add_edge("finalize_pending_approval", END)

    return g.compile(checkpointer=checkpointer)
