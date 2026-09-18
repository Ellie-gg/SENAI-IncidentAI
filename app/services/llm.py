"""Cliente de LLM configurável por variável de ambiente (`LLM_PROVIDER`).

Nenhum nó do grafo importa `langchain_google_genai` diretamente — todos
falam com o `Protocol` `LLMClient` definido aqui. Isso é o que permite
`LLM_PROVIDER=mock` rodar a suíte inteira offline, sem chave de API: o
`MockLLMClient` implementa o mesmo contrato com heurísticas determinísticas
por palavra-chave, incluindo o caminho de "saída estruturada" — que é
justamente o ponto onde um fake ingênuo (que só implementa `_generate`)
quebra.

`structured_with_fallback` implementa a escada de degradação: tentativa
estruturada -> retry -> extração de JSON via regex no texto bruto ->
degradado. Isolado aqui para ser testável sem subir o grafo inteiro.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from app.config import get_settings
from app.models.llm_io import AnalysisOut, IncidentCategory, RecommendationOut

T = TypeVar("T", bound=BaseModel)

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


class LLMClient(Protocol):
    async def structured(self, schema: type[T], prompt: str) -> T: ...

    async def raw_text(self, prompt: str) -> str: ...


class LLMUnavailableError(RuntimeError):
    """Levantado quando o provedor não consegue produzir nenhuma saída."""


# --------------------------------------------------------------------------
# Gemini (produção)
# --------------------------------------------------------------------------


class GeminiLLMClient:
    """Wrapper fino sobre `ChatGoogleGenerativeAI`. Instanciado só quando
    `LLM_PROVIDER=gemini` — importar `langchain_google_genai` custa tempo de
    startup e exige a lib mesmo quando não usada."""

    def __init__(self, *, model: str, api_key: str) -> None:
        from langchain_google_genai import ChatGoogleGenerativeAI

        self._model_name = model
        self._chat = ChatGoogleGenerativeAI(model=model, google_api_key=api_key, temperature=0)

    async def structured(self, schema: type[T], prompt: str) -> T:
        # method="json_schema" (default) usa o response_schema nativo do
        # Gemini — mais confiável que function_calling para schemas simples
        # e achatados (ver app/models/llm_io.py para o motivo do formato).
        structured_model = self._chat.with_structured_output(schema)
        result = await structured_model.ainvoke(prompt)
        if isinstance(result, schema):
            return result
        return schema.model_validate(result)

    async def raw_text(self, prompt: str) -> str:
        message = await self._chat.ainvoke(prompt)
        content = message.content
        return content if isinstance(content, str) else str(content)


# --------------------------------------------------------------------------
# Mock (default — testes, CI, demo offline)
# --------------------------------------------------------------------------

_CATEGORY_KEYWORDS: dict[IncidentCategory, tuple[str, ...]] = {
    "database_connectivity": (
        "connection pool",
        "database",
        "db connection",
        "postgres",
        "mysql",
        "sql",
    ),
    "memory_pressure": ("out of memory", "oom", "memory pressure", "heap"),
    "latency_degradation": ("latency", "slow response", "timeout", "p95", "p99"),
    "deployment_regression": ("deploy", "rollout", "release", "rollback"),
    "dependency_failure": ("upstream", "third-party", "dependency", "external api"),
    "auth_failure": ("401", "403", "unauthorized", "auth failure", "token expired"),
    "disk_capacity": ("disk full", "no space left", "disk capacity", "storage"),
    "network": ("network", "dns", "connection refused", "packet loss"),
}

_CATEGORY_ACTIONS: dict[IncidentCategory, tuple[str, ...]] = {
    "database_connectivity": (
        "Check database availability and active connection count",
        "Inspect connection pool utilization and max_size configuration",
        "Review recent deployment changes touching the data layer",
    ),
    "memory_pressure": (
        "Inspect heap/memory usage graphs for the affected service",
        "Check for recent code changes introducing memory leaks",
        "Consider a controlled restart to relieve pressure while investigating",
    ),
    "latency_degradation": (
        "Compare current p95/p99 latency against baseline",
        "Check downstream dependencies for slow responses",
        "Review recent traffic changes or new heavy queries",
    ),
    "deployment_regression": (
        "Compare error rate before/after the most recent deploy",
        "Consider rolling back to the previous known-good version",
        "Review the diff of the last deployment for suspicious changes",
    ),
    "dependency_failure": (
        "Check the status page of the affected upstream dependency",
        "Verify retry/circuit-breaker configuration for that dependency",
        "Confirm whether a fallback path exists and is active",
    ),
    "auth_failure": (
        "Check for expired credentials, tokens or certificates",
        "Verify the identity provider / auth service health",
        "Review recent changes to auth configuration or secrets rotation",
    ),
    "disk_capacity": (
        "Check disk usage on the affected host/volume",
        "Identify and rotate/purge large log or temp files",
        "Verify autoscaling or volume expansion policies",
    ),
    "network": (
        "Check DNS resolution and connectivity from the affected service",
        "Review recent network/firewall/security-group changes",
        "Verify load balancer and service mesh health",
    ),
    "unknown": (
        "Manually review the provided logs and description",
        "Check the service's dashboard for anomalies",
        "Escalate to the on-call engineer for the affected service",
    ),
}


def default_actions_for_category(category: str) -> list[str]:
    """Fallback estático usado quando `generate_recommendation` degrada
    (parse de saída estruturada falhou 3x) — nunca deixa a resposta sem
    ações recomendadas."""
    return list(_CATEGORY_ACTIONS.get(category, _CATEGORY_ACTIONS["unknown"]))


def _classify_category(text: str) -> tuple[IncidentCategory, bool]:
    lowered = text.lower()
    for category, keywords in _CATEGORY_KEYWORDS.items():
        if any(kw in lowered for kw in keywords):
            return category, True
    return "unknown", False


class MockLLMClient:
    """Heurísticas determinísticas por palavra-chave. Implementa o mesmo
    Protocol que o Gemini real, incluindo `structured()` — o requisito que
    quebra fakes ingênuos que só sabem responder texto livre."""

    def __init__(self, *, always_fail: bool = False) -> None:
        self._always_fail = always_fail

    async def structured(self, schema: type[T], prompt: str) -> T:
        if self._always_fail:
            raise LLMUnavailableError("mock_fail: structured output indisponível (proposital)")

        if schema is AnalysisOut:
            category, matched = _classify_category(prompt)
            signals = [
                line.strip()[:120]
                for line in prompt.splitlines()
                if any(kw in line.lower() for kw in _CATEGORY_KEYWORDS.get(category, ()))
            ][:5]
            return schema(  # type: ignore[return-value]
                category=category,
                probable_cause=(
                    f"Padrão de log/descrição consistente com {category.replace('_', ' ')}"
                    if matched
                    else "Causa não identificada claramente a partir dos sinais disponíveis"
                ),
                confidence=0.85 if matched else 0.3,
                key_signals=signals or ["Sem sinais textuais fortes identificados"],
            )

        if schema is RecommendationOut:
            category, _ = _classify_category(prompt)
            actions = list(_CATEGORY_ACTIONS.get(category, _CATEGORY_ACTIONS["unknown"]))
            return schema(  # type: ignore[return-value]
                summary=f"Recomendações determinísticas (mock) para categoria '{category}'.",
                recommended_actions=actions,
            )

        raise LLMUnavailableError(f"MockLLMClient não sabe simular o schema {schema!r}")

    async def raw_text(self, prompt: str) -> str:
        if self._always_fail:
            # Simula uma resposta "malformada" — não é JSON, então a
            # extração via regex no attempt 3 também falha, forçando
            # degraded=True de ponta a ponta (é o que mock_fail existe para testar).
            return "I could not analyze this incident right now."

        category, matched = _classify_category(prompt)
        payload = {
            "category": category,
            "probable_cause": "Mock raw_text fallback",
            "confidence": 0.5 if matched else 0.2,
            "key_signals": [],
        }
        return json.dumps(payload)


# --------------------------------------------------------------------------
# Fábrica
# --------------------------------------------------------------------------


@lru_cache
def get_llm() -> LLMClient:
    settings = get_settings()
    if settings.llm_provider == "gemini":
        if not settings.google_api_key:
            raise LLMUnavailableError(
                "LLM_PROVIDER=gemini requer GOOGLE_API_KEY configurada (.env, nunca no código)."
            )
        return GeminiLLMClient(model=settings.llm_model, api_key=settings.google_api_key)
    if settings.llm_provider == "mock_fail":
        return MockLLMClient(always_fail=True)
    return MockLLMClient(always_fail=False)


async def structured_with_fallback(
    client: LLMClient, schema: type[T], prompt: str, *, structured_attempts: int = 2
) -> tuple[T | None, bool]:
    """Escada de degradação: (1) tentativa(s) de saída estruturada, (2)
    extração de JSON via regex no texto bruto, (3) degraded=True.
    O chamador (nós do grafo) decide o valor estático de fallback quando
    `degraded` volta True — nunca propaga exceção para a API."""
    last_error: Exception | None = None

    for _ in range(max(1, structured_attempts)):
        try:
            return await client.structured(schema, prompt), False
        except (ValidationError, LLMUnavailableError, Exception) as exc:  # noqa: BLE001
            last_error = exc
            continue

    try:
        text = await client.raw_text(
            prompt + "\n\nReturn ONLY a single valid JSON object matching the required schema."
        )
        match = _JSON_BLOCK.search(text)
        if match:
            candidate: Any = json.loads(match.group(0))
            return schema.model_validate(candidate), False
    except (ValidationError, json.JSONDecodeError, Exception) as exc:  # noqa: BLE001
        last_error = exc

    _ = last_error  # registrado pelo chamador via app.observability.logger
    return None, True
