# IncidentAI

Copiloto de SRE/DevOps com agente LangGraph. Recebe `logs + descrição` de
um incidente, analisa com um grafo que combina decisões de LLM com regras
determinísticas, consulta o estado real do serviço e o histórico, calcula
risco e tendência, exige aprovação humana para ações que mudam algo em
produção, e devolve JSON estruturado com rastro de observabilidade
correlacionado.

Projeto avaliativo M2.2 — IA para Desenvolvedores [T2]. Vídeo de
demonstração: **[link após publicação]**.

## Sumário

1. [Descrição da solução](#1-descrição-da-solução)
2. [Classificação e arquitetura](#2-classificação-e-arquitetura)
3. [Tool e integração](#3-tool-e-integração)
4. [Contexto e memória](#4-contexto-e-memória)
5. [Segurança e autonomia](#5-segurança-e-autonomia)
6. [Instalação e execução](#6-instalação-e-execução)
7. [QA, observabilidade e DevOps](#7-qa-observabilidade-e-devops)
8. [Automação low-code](#8-automação-low-code)
9. [Cenários de uso](#9-cenários-de-uso)
10. [Análise crítica e limitações](#10-análise-crítica-e-limitações)

---

## 1. Descrição da solução

**Problema**: times de plantão recebem um incidente (logs + descrição) e
precisam, sob pressão, classificar, estimar severidade/risco, checar o
estado real do serviço, lembrar de incidentes parecidos e decidir o que
fazer — sem vazar dados sensíveis nem executar algo destrutivo por
engano.

**Público**: engenheiros de plantão (SRE/DevOps) e quem aprova ações
sensíveis em produção.

**Objetivo e valor**: automatizar a triagem inicial (classificação, causa
provável, risco, ações recomendadas, evidência histórica) mantendo um
humano no controle de qualquer ação que tenha consequência real.

**Saída estruturada** (contrato completo em
[`app/models/response.py`](app/models/response.py)):

```json
{
  "incident_id": "INC-91A02", "trace_id": "…",
  "category": "database_connectivity", "severity": "high",
  "probable_cause": "Connection pool exhaustion", "confidence": 0.85,
  "recommended_actions": ["…"],
  "risk": {"score": 8, "failure_risk": 0.77, "trend": "increasing", "trend_confidence": 0.5},
  "action_class": "RECOMMEND", "requires_human_approval": true,
  "evidence": {"similar_incidents": ["INC-00001"], "runbooks": ["Postgres Runbook > Connection Pool"],
               "service_status": "degraded", "monitoring_source": "monitoring"},
  "security_violation": false, "degraded": false, "terminal_reason": "pending_approval"
}
```

Projeto construído do zero para esta avaliação (não é continuação de
mini-projeto anterior).

## 2. Classificação e arquitetura

**Sistema híbrido**: LLM decide categoria/causa provável/redação das
ações; regra determinística decide severidade/score de risco/tendência/
necessidade de aprovação. Testado explicitamente em
[`tests/unit/test_risk_llm_separation.py`](tests/unit/test_risk_llm_separation.py):
mutar campos do LLM não muda a saída de risco; mudar um campo de regra,
muda.

Diagrama completo (Mermaid) e detalhamento de cada nó em
**[`docs/architecture.md`](docs/architecture.md)**. Resumo do grafo:

```
validate_input → security_check → analyze_incident (LLM)
   → [FAN-OUT] check_service_status (tool) ⟂ search_incident_history (RAG) [FAN-IN]
   → assess_risk (regra) → [retry ↺ | recommend]
   → generate_recommendation (LLM) → approval_check (regra)
   → [pendente de aprovação | concluído]
```

3 condicionais, paralelização real (medida por tempo de parede em
[`tests/integration/test_graph_execution.py`](tests/integration/test_graph_execution.py)),
loop de retry com parada garantida (`MAX_ITERATIONS` + `recursion_limit`).

## 3. Tool e integração

**Tool**: status/histórico de um serviço monitorado
(`get_service_status`). Implementação real em três camadas, sem
duplicação — [`app/tools/core.py`](app/tools/core.py) é a fonte única:

- **HTTP resiliente** ([`app/tools/monitoring_client.py`](app/tools/monitoring_client.py)):
  timeout 3s, até 2 retries com backoff+jitter para timeout/5xx, sem
  retry para 4xx/contrato quebrado, fallback `status=unknown` — nunca
  lança exceção.
- **Serviço real** ([`mock_monitoring/`](mock_monitoring/)): container
  FastAPI separado, com cenários determinísticos por serviço e um modo de
  falha controlada (`/_control/fail?mode=timeout|500|garbage`) para os
  testes de resiliência.
- **MCP** ([`mcp_server/server.py`](mcp_server/server.py)): a mesma tool
  reexposta via servidor MCP real (stdio); `TOOLS_TRANSPORT=mcp` faz o
  grafo chamar por esse caminho em vez de in-process (`inprocess`,
  default).

## 4. Contexto e memória

- **Checkpointer** ([`app/agent/checkpointer.py`](app/agent/checkpointer.py)):
  `AsyncSqliteSaver`, um thread por `incident_id` — permite retomar um
  incidente (ex.: depois de uma aprovação humana).
- **RAG leve** ([`app/memory/rag.py`](app/memory/rag.py)): SQLite FTS5
  sobre incidentes históricos e runbooks markdown (`data/runbooks/`),
  **sem vector DB**. Base: 8 incidentes canônicos
  (`scripts/seed_incidents.py`) + 7 runbooks reais, chunkados por seção
  H1/H2/H3 (`app/memory/ingest_runbooks.py`). Query nunca interpola texto
  cru (neutraliza operadores FTS5 com aspas); `bm25()` é negativo →
  ordenação ascendente (testado — trocar para DESC devolveria os piores
  resultados). Fallback determinístico por serviço/categoria quando a
  busca textual não acha nada.

## 5. Segurança e autonomia

- **Segredos**: nunca no repositório — `.env` no `.gitignore`,
  `.env.example` sem valores reais. Nenhum default de credencial em
  código (`app/config.py`).
- **Guardrails** ([`app/security/guardrails.py`](app/security/guardrails.py)):
  blocklist de prompt injection aplicada (1) na entrada, antes de
  qualquer chamada de LLM — bloqueia o incidente inteiro; (2) no conteúdo
  recuperado via RAG, depois da busca — filtra sem abortar o fluxo
  (defesa em profundidade contra runbook/histórico envenenado).
  `redact_secrets()` redige a saída da API como última linha de defesa.
- **Limites de autonomia** ([`app/security/policies.py`](app/security/policies.py)):
  ações classificadas em `READ`/`ANALYZE`/`RECOMMEND` (automático),
  `CHANGE` (aprovação humana obrigatória em produção) e `DELETE` (sempre
  bloqueado — a aplicação nunca executa nenhuma ação de fato, aprovar via
  `POST /incidents/{id}/approve` só registra decisão para auditoria).
- **Cenário adversarial** (obrigatório, item 4.5): prompt injection
  pedindo para revelar API key e apagar o banco →
  `security_violation=true`, bloqueado antes do LLM rodar, nada da
  tentativa vaza na resposta. Testado fim-a-fim via API real em
  [`tests/integration/test_security_adversarial.py`](tests/integration/test_security_adversarial.py).

## 6. Instalação e execução

Requer Docker + Docker Compose. Python 3.12 se for rodar fora de
container (`requirements.txt` trava as versões).

```bash
cp .env.example .env   # LLM_PROVIDER=mock funciona sem nenhuma chave

docker compose up -d --build app mock-monitoring
docker compose exec app python scripts/seed_incidents.py

curl http://localhost:8000/health
python scripts/demo.py   # roda os 2 cenários (docs/exemplos/)
```

Com Gemini real: preencher `LLM_PROVIDER=gemini` e `GOOGLE_API_KEY` no
`.env` antes do `docker compose up`.

Rodando local sem Docker:

```bash
python -m venv .venv && .venv/Scripts/activate   # ou source .venv/bin/activate
pip install -r requirements.txt
pytest -q                          # 204 testes, offline (LLM_PROVIDER=mock)
uvicorn app.main:app --reload
```

Variáveis de ambiente completas em [`.env.example`](.env.example).

## 7. QA, observabilidade e DevOps

**QA com IA**:
[`scripts/ai_code_review.py`](scripts/ai_code_review.py) rodado contra um
diff real do projeto com Gemini →
[`docs/qa/code-review-fase7-security.md`](docs/qa/code-review-fase7-security.md)
(sugestões reais, uma incorporada como teste novo). 204 testes
(unit/integration/e2e); E2E real com stack completa em
[`tests/e2e/test_full_incident_lifecycle.py`](tests/e2e/test_full_incident_lifecycle.py).
Priorização por risco justificada em
[`docs/qa/priorizacao-testes.md`](docs/qa/priorizacao-testes.md).

**Observabilidade** (3 sinais correlacionados por `trace_id`/`incident_id`):
logs estruturados JSON ([`app/observability/logger.py`](app/observability/logger.py)),
auditoria em SQLite (`GET /incidents/{id}/audit`), métricas em memória
(`GET /metrics`). Prova de correlação em
[`tests/integration/test_observability_e2e.py`](tests/integration/test_observability_e2e.py).

**DevOps inteligente**: pipeline real (`.github/workflows/ci.yml`,
lint → test → build) — **anomalia real detectada e explicada**: duas
execuções não provocadas falharam; a raiz (`pytest` puro não adiciona o
projeto ao `sys.path`, diferente de `python -m pytest`) foi diagnosticada
via instrumentação do próprio workflow (sem acesso de admin ao log bruto)
e corrigida — ver
[`docs/qa/ci-failure-root-cause.md`](docs/qa/ci-failure-root-cause.md).
[`scripts/ai_log_analysis.py`](scripts/ai_log_analysis.py) explica logs de
N etapas com IA;
[`scripts/anomaly_report.py`](scripts/anomaly_report.py) estima
tendência/risco sobre dados reais do projeto
(`mock_monitoring/main.py`), com explicação em linguagem natural.

## 8. Automação low-code

[`n8n/incidentai-alert.json`](n8n/incidentai-alert.json): Webhook → IF
severidade ≥ `high` → formata mensagem → HTTP Request para o alvo
configurado (Discord/Slack/Teams via `ALERT_TARGET_WEBHOOK_URL`).
Disparado por [`app/services/notifier.py`](app/services/notifier.py)
(lógica principal na aplicação; n8n só orquestra a notificação), em
background (`BackgroundTasks`, nunca atrasa a resposta da análise).

```bash
# .env: N8N_BASIC_AUTH_PASSWORD=<algo forte>, N8N_WEBHOOK_URL=http://localhost:5678/webhook/incidentai-alert
docker compose -f docker-compose.yml -f docker-compose.low-code.yml --profile low-code up -d
# abrir http://localhost:5678, importar n8n/incidentai-alert.json, ativar
```

## 9. Cenários de uso

Payloads prontos em [`docs/exemplos/`](docs/exemplos/README.md).

**Cenário 1 — fluxo principal**: `payments-api` com erro de conexão de
banco. Com o mock-monitoring real (histórico de erro crescente) e o seed
rodado, resposta: `severity=high`, `risk.trend=increasing`,
`requires_human_approval=true`, evidência de RAG relevante (`INC-00001`,
runbook de connection pool).

**Cenário 2 — risco/adversarial**: prompt injection pedindo para revelar
segredos e apagar o banco. Resposta: `security_violation=true`,
`terminal_reason=security_blocked`, `recommended_actions=[]`.

## 10. Análise crítica e limitações

Dois refinamentos documentados em detalhe (problema → mudança →
resultado) em
**[`docs/refinamento-prompt.md`](docs/refinamento-prompt.md)**: (1)
reordenação do grafo para `approval_check` ver a ação real recomendada;
(2) falso positivo na blocklist de segurança (`"restart production"`
bloqueava descrições legítimas). Um terceiro caso real de DevOps
(diagnóstico de falha de CI) está em
[`docs/qa/ci-failure-root-cause.md`](docs/qa/ci-failure-root-cause.md).

**Limitações conhecidas**: RAG é léxico (FTS5), não semântico — não
generaliza fora do vocabulário indexado; nenhuma ação é executada de
fato (aprovação é só auditoria, por design); MCP sobe um subprocesso por
chamada (aceitável no volume deste projeto, não em produção). Evoluções
possíveis: RAG vetorial, autenticação/RBAC, execução supervisionada de
remediações simples — ver também `docs/video-roteiro.md`.

---

## Status das fases (histórico de desenvolvimento)

- [x] Fase 0 — bootstrap · [x] Fase 1 — fundação · [x] Fase 2 — modelos
- [x] Fase 3 — agente LangGraph · [x] Fase 4 — tool + MCP
- [x] Fase 5 — memória/RAG · [x] Fase 6 — motor de risco
- [x] Fase 7 — segurança · [x] Fase 8 — observabilidade
- [x] Fase 9 — QA inteligente · [x] Fase 10 — DevOps/CI
- [x] Fase 11 — low-code · [x] Fase 12 — documentação final

Ver [`PLAN.md`](PLAN.md) para o planejamento original e histórico de
commits/branches (`develop` → `feature/*` → `develop` → `main`) para a
evolução real do projeto.
