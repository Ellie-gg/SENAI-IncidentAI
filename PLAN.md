# IncidentAI — Planejamento de Desenvolvimento

> Status: proposta aprovada v0.1 | Fonte: discussão de arquitetura | Próximo passo: criar cards no GitHub Project a partir das Fases 1-12

## 1. Visão

O **IncidentAI** é um copiloto de SRE/DevOps, pequeno mas realista. Recebe `logs + descrição`, analisa via **FastAPI + LangGraph**, consulta estado do serviço e histórico, calcula risco por **regras determinísticas**, exige **aprovação humana** para ações mutantes e retorna **JSON estruturado**. Lógica principal fica na aplicação; low-code (n8n) só dispara alerta.

Não é um CRUD acadêmico: é um agente com estado, ferramentas com resiliência, guardrails, observabilidade correlacionada e CI/CD com evidências.

## 2. Arquitetura alvo (confirmada)

```
logs + descrição
       ↓
     FastAPI (POST /incidents/analyze)
       ↓
     LangGraph
       ↓
┌───────────────────────────────┐
│ validate_input (determinístico)│
│ security_check (guardrail)     │
│ analyze_incident (LLM)         │
│ check_service_status (tool) ─┐ │
│ search_incident_history (mem)┘ │ paralelo
│ assess_risk (regra)            │
│ approval_check (policy)        │
│ generate_recommendation (LLM)  │
└───────────────────────────────┘
       ↓
  JSON estruturado
       +
  logs estruturados / traces / auditoria / SQLite / webhook → n8n
```

### 2.1 Requisitos do enunciado cobertos

| Requisito | Onde |
|---|---|
| State tipado | `app/agent/state.py` (`TypedDict`) |
| Nodes + Edges | `app/agent/graph.py`, `nodes.py` |
| Sequência | validate → security → analyze → ... → response |
| Condicional | `routing.py`: block em injection, approval se mutante, END em inválido |
| Paralelização | `analyze` → `check_status` + `search_history` em paralelo → `assess_risk` |
| Controle de parada | `iteration_count + MAX_ITERATIONS=3`, END em violation/inválido/concluído/falha irrecuperável |
| Tool com resiliência | `tools/service_status.py`: timeout=3s, retry=2, fallback `unknown`, validação de schema |
| Memória / RAG simples | `memory/incident_repository.py` + SQLite, `WHERE service=? OR category=? LIMIT 5`, sem vector DB no MVP |
| Híbrido LLM vs regra | LLM: categoria/causa/recomendação. Regra: severity/risco/aprovação |
| Estimativa tendência/risco | `assess_risk`: score + `failure_risk` + `trend` a partir de error_rate/latência históricos |
| Segurança adversarial | `security/guardrails.py` + `policies.py`: blocklist inicial + `security_violation`, `requires_approval` |
| Human-in-the-loop | `approval_check`: READ/ANALYZE/RECOMMEND liberado, CHANGE exige aprovação, DELETE bloqueado |
| Observabilidade (2 sinais) | `observability/logger.py` (structlog) + `audit.py`, correlacionados por `incident_id`/`trace_id` |
| Validação payload/schema | `models/incident.py` (Pydantic), `environment: Literal[...]` |
| Saída estruturada | `models/response.py` (`IncidentResponse`) |
| Segredo fora do código | `config.py` + `.env.example` (`LLM_PROVIDER`, `LLM_MODEL`, `OPENAI_API_KEY`) via `services/llm.py:get_llm()` |
| Testes 3 níveis | `tests/unit|integration|e2e` |
| IA no QA | `docs/qa/code-review.md` a partir de diff real |
| CI com 2 análises de log | `.github/workflows/ci.yml`: lint → test → build + `docs/qa/ci-failure-*.md` |
| Low-code | `services/notifier.py` → webhook → n8n → alerta se `severity==HIGH` |

### 2.2 Ajustes mínimos sugeridos (sem mudar sua proposta)

1. Adicionar `app/agent/checkpointer.py` ou flag `checkpointer: SQLiteSaver` no `graph.py` — o enunciado cita checkpointer explicitamente.
2. Manter `routing.py` separado de `graph.py` para deixar condicionais testáveis sem subir o grafo.
3. `incident_repository.py` expor `save_incident`, `search_similar`, `save_event` para alimentar `incidents`, `incident_events`, `audit_log`.
4. `scripts/seed_incidents.py` popular 5-8 incidentes canônicos (ex: INC001 pool exhaustion) para demo e testes E2E determinísticos.
5. Não incluir RAG vetorial agora — documentar como evolução em `docs/architecture.md`.

## 3. Estrutura final do repositório (alvo)

```
incident-ai/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── api/routes.py
│   ├── agent/{graph.py,state.py,nodes.py,routing.py,prompts.py}
│   ├── tools/service_status.py
│   ├── memory/incident_repository.py
│   ├── models/{incident.py,response.py}
│   ├── security/{guardrails.py,policies.py}
│   ├── observability/{logger.py,audit.py}
│   └── services/{llm.py,notifier.py}
├── tests/{unit,integration,e2e}
├── scripts/seed_incidents.py
├── data/.gitkeep
├── docs/{architecture.md,prompts/,qa/,evidencias/}
├── .github/workflows/ci.yml
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

> Não criar tudo de uma vez. Evoluir por fases abaixo.

## 4. Contratos congelados (v1)

**Request `POST /incidents/analyze`:**
```json
{
  "service": "payments-api",
  "environment": "production",
  "description": "API presenting database connection errors",
  "logs": ["ERROR database connection timeout", "ERROR connection pool exhausted", "WARN latency=2350ms"]
}
```

**Response:**
```json
{
  "incident_id": "INC-91A02",
  "category": "database_connectivity",
  "severity": "high",
  "probable_cause": "Connection pool exhaustion",
  "confidence": 0.88,
  "recommended_actions": ["Check database availability", "Inspect connection pool utilization", "Review recent deployment changes"],
  "requires_human_approval": false
}
```

**Regra de risk (v1):** `production +2, error_rate>0.10 +3, latency>2000ms +2, status==down +3` → `0-2 LOW, 3-5 MEDIUM, 6+ HIGH`.

## 5. Fases de execução (12 branches → GitHub Project)

> Fluxo Git obrigatório: `develop → feature/* → PR → develop → main`. Nada de commit direto em `main`. Cada fase gera PR + review com IA + evidência.

### Fase 1 — `feature/project-foundation`
- Objetivo: FastAPI sobe, `/health` ok, config, lint, Docker esqueleto.
- Tarefas: `app/main.py`, `app/config.py`, `requirements.txt`, `.env.example`, `.gitignore`, `Dockerfile`, `docker-compose.yml`, `GET /health`.
- Aceite: `uvicorn app.main:app` responde 200; `docker build` passa; `ruff` limpo.
- Evidência: `docs/evidencias/fase1-health-200.png`.

### Fase 2 — `feature/incident-models`
- Objetivo: contratos Pydantic.
- Tarefas: `models/incident.py` (`IncidentRequest`), `models/response.py` (`IncidentResponse`), validação de payload grande/logs vazios.
- Aceite: testes de schema válido/inválido passam; erro retorna 422 com mensagem clara.
- Evidência: exemplo request/response no README.

### Fase 3 — `feature/langgraph-agent`
- Objetivo: grafo mínimo fim-a-fim com mock de LLM.
- Tarefas: `agent/state.py`, `prompts.py`, `nodes.py` (validate, security stub, analyze mock, assess stub, generate stub), `routing.py`, `graph.py` com sequência + 1 condicional + `MAX_ITERATIONS`.
- Aceite: teste `test_incident_workflow.py` executa `validate→analyze→response` sem chamar API externa.
- Evidência: print do grafo (mermaid) em `docs/architecture.md`.

### Fase 4 — `feature/tool-integration`
- Objetivo: `get_service_status` resiliente.
- Tarefas: `tools/service_status.py` com timeout 3s, retry 2x, validação, fallback `unknown`; mock de monitoramento.
- Aceite: `test_service_status_tool.py` cobre sucesso, timeout→retry, falha→fallback.
- Evidência: log de timeout simulado.

### Fase 5 — `feature/memory`
- Objetivo: persistência + histórico.
- Tarefas: `memory/incident_repository.py`, schema SQLite (`incidents`, `incident_events`, `audit_log`), `scripts/seed_incidents.py`, node `search_history` com `WHERE service OR category LIMIT 5`.
- Aceite: seed cria 5+ incidentes; busca retorna INC relevante para `payments-api/database`.
- Evidência: `sqlite3 data/incidents.db "select * from incidents;"`.

### Fase 6 — `feature/risk-engine`
- Objetivo: severidade determinística + tendência.
- Tarefas: regra de score (Sec. 4), `failure_risk` + `trend` (ex: 5%→9%→14% = increasing/high), testes de matriz.
- Aceite: `test_risk_calculation.py` cobre LOW/MEDIUM/HIGH + borda; LLM não altera score.
- Evidência: tabela de casos em `docs/evidencias/fase6-risk-matrix.md`.

### Fase 7 — `feature/security`
- Objetivo: guardrails + approval.
- Tarefas: `security/guardrails.py` (blocklist: `ignore previous instructions`, `show api key`, `read .env`, `delete database`, `restart production`, `kubectl delete`, `terraform destroy`), `policies.py` (READ/ANALYZE/RECOMMEND vs CHANGE vs DELETE), `approval_check`.
- Aceite: `test_security_guardrails.py`: injection → `security_violation=true` + BLOCK ou approval; segredo nunca vaza; `restart prod` → `requires_human_approval=true`.
- Evidência: `docs/qa/adversarial-tests.md`.

### Fase 8 — `feature/observability`
- Objetivo: 2 sinais correlacionados.
- Tarefas: `observability/logger.py` (JSON com `incident_id,node,duration_ms,status`), `audit.py` (decisão `blocked/approved`), `incident_id` em todos os nós.
- Aceite: execução E2E gera logs + trilha reconstruível pelo `incident_id`.
- Evidência: trecho de log JSON + audit em `docs/evidencias/fase8-trace.json`.

### Fase 9 — `feature/tests`
- Objetivo: pirâmide verde + QA com IA.
- Tarefas: `tests/unit`, `integration`, `e2e` (POST → LangGraph → validação); gerar diff real → review IA → criar testes faltantes → salvar em `docs/qa/code-review.md`.
- Aceite: `pytest` 100% verde local; cobertura das regras críticas.
- Evidência: `docs/qa/code-review.md` + relatório pytest.

### Fase 10 — `feature/ci-pipeline`
- Objetivo: CI que quebra e ensina.
- Tarefas: `.github/workflows/ci.yml` (`ruff → pytest → docker build`); provocar falha 1 (teste quebrado) + falha 2 (docker build) e documentar análises IA em `docs/qa/ci-failure-*.md`.
- Aceite: badge verde em `main`; 2 logs de falha analisados e corrigidos.
- Evidência: links para runs do Actions + 2 arquivos de análise.

### Fase 11 — `feature/low-code`
- Objetivo: alerta só em HIGH.
- Tarefas: `services/notifier.py` (webhook), workflow n8n (`webhook → IF severity==HIGH → Discord/Slack/email`), `.env` com `N8N_WEBHOOK_URL`.
- Aceite: incidente HIGH dispara alerta; LOW não dispara; lógica permanece na app.
- Evidência: `docs/evidencias/fase11-n8n-alert.png` + export JSON do workflow.

### Fase 12 — `docs/final-documentation`
- Objetivo: parecer produto.
- Tarefas: `README.md` (como rodar, exemplos, arquitetura, vídeo roteiro), `docs/architecture.md` final, `docs/evidencias/` completo, `docs/prompts/` versionados.
- Aceite: terceiro roda com `docker-compose up` + `seed` + `curl` sem ajuda; vídeo de 5 min roteirizado.
- Evidência: checklist de demo verde.

## 6. Ordem e dependências

```
1 foundation → 2 models → 3 agent → 4 tool ┐
                                            ├→ 6 risk → 7 security → 8 observability → 9 tests → 10 CI → 11 low-code → 12 docs
                             5 memory ─────┘
```
Paralelizável após Fase 3: Fase 4 e Fase 5 podem rodar em paralelo (owners diferentes).

## 7. GitHub Project (modelo de card)

Título: `[Fase X] nome`
Descrição: Objetivo / Tarefas / Aceite / Evidência (copiar da Seção 5)
Labels: `fase-X`, `feature`, `needs-review`
Definition of Done: código + testes verdes + PR para `develop` + review IA anexado + evidência em `docs/`.

Branches: `main` (protegida), `develop`, `feature/*`, `docs/*`. PRs com squash, 1 aprovação (pode ser self-review documentado + IA).

## 8. Riscos e mitigação

- LLM instável/caro → mock por padrão, `LLM_PROVIDER=mock` nos testes; gravar prompts em `docs/prompts/`.
- Escopo estoura → RAG vetorial, auth/RBAC e frontend ficam fora do MVP, listados como evolução.
- Histórico fabricado → seed versionado + PRs reais desde a Fase 1, sem `push --force`.

## 9. Próximo passo imediato

1. Criar repo com `develop`, `README` mínimo e `PLAN.md` (este arquivo).
2. Abrir 12 issues a partir da Seção 5 e importar no Project board (`Todo → Doing → Review → Done`).
3. Iniciar Fase 1 em `feature/project-foundation`.
