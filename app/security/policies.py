"""Classificação de ação e política de aprovação humana — limites de
autonomia da aplicação.

`READ` / `ANALYZE` / `RECOMMEND`: automático, sem consequência real (a
aplicação só lê dados e sugere).
`CHANGE`: exige aprovação humana em produção — a aplicação nunca executa,
só recomenda; aprovação aqui é registro de governança (audit trail), não
disparo de ação.
`DELETE`: sempre bloqueado. A aplicação nunca gera nem permite uma ação de
deleção — mesmo "aprovada", ela nunca seria executada (não há nenhum
código neste projeto que execute ações remotas; tudo é recomendação).
"""

from __future__ import annotations

from typing import Literal

ActionClass = Literal["READ", "ANALYZE", "RECOMMEND", "CHANGE", "DELETE"]

_DELETE_KEYWORDS = ("delete", "drop ", "truncate", "rm -rf", "destroy", "purge", "terminate")
_CHANGE_KEYWORDS = (
    "restart",
    "rollback",
    "scale",
    "kill",
    "reboot",
    "redeploy",
    "revert",
    "disable",
    "enable",
    "rotate",
    "roll back",
)


def classify_action(actions: list[str]) -> ActionClass:
    text = " ".join(actions).lower()
    if any(kw in text for kw in _DELETE_KEYWORDS):
        return "DELETE"
    if any(kw in text for kw in _CHANGE_KEYWORDS):
        return "CHANGE"
    if actions:
        return "RECOMMEND"
    return "READ"


def is_destructive(action_class: ActionClass) -> bool:
    return action_class == "DELETE"


def requires_approval(
    *,
    action_class: ActionClass,
    environment: str,
    severity: str,
    llm_parse_failed: bool,
    security_violation: bool,
) -> bool:
    if security_violation:
        # já bloqueado antes de chegar aqui (finalize_blocked) — não faz
        # sentido também pedir aprovação para algo que nunca vai rodar.
        return False
    if action_class == "DELETE":
        return True
    if llm_parse_failed:
        # análise degradada (LLM falhou 3x) nunca é auto-acionada, mesmo
        # que a ação recomendada pareça inofensiva.
        return True
    if action_class == "CHANGE" and environment == "production":
        return True
    return severity in ("high", "critical") and environment == "production"
