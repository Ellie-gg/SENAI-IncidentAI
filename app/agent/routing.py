"""Funções de aresta condicional — separadas de `graph.py` de propósito,
para serem testáveis sem subir o grafo inteiro (bastam dicts simulando
`IncidentState`).
"""

from __future__ import annotations

from app.agent.state import IncidentState
from app.config import get_settings


def route_after_validate(state: IncidentState) -> str:
    return "ok" if state.get("is_valid", False) else "invalid"


def route_after_security(state: IncidentState) -> str:
    return "block" if state.get("security_violation", False) else "continue"


def route_after_approval(state: IncidentState) -> str:
    """Condicional #2 + condição de parada do loop de retry.

    `iteration_count < MAX_ITERATIONS` é a rede de segurança principal;
    `recursion_limit` no invoke (app/agent/graph.py) é a rede de segurança
    secundária caso esta condição tenha algum bug de wiring.
    """
    settings = get_settings()
    if state.get("requires_human_approval", False):
        return "needs_approval"
    if (
        state.get("needs_reanalysis", False)
        and state.get("iteration_count", 0) < settings.max_iterations
    ):
        return "retry"
    return "auto"
