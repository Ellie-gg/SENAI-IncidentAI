# Roteiro do vídeo de demonstração (≤ 12 min)

> Link do vídeo publicado: **[preencher após gravar e publicar no YouTube como não listado]**

## 0:00 – 1:00 · Problema, objetivo e classificação

- IncidentAI: copiloto de SRE/DevOps. Recebe `logs + descrição`, devolve
  categoria, causa provável, severidade, risco de falha e ações
  recomendadas — com aprovação humana obrigatória para ações que mudam
  algo em produção.
- Classificação: **sistema híbrido** — LLM decide narrativa (categoria,
  causa, redação); regra decide consequência (severidade, risco,
  aprovação). Mostrar `tests/unit/test_risk_llm_separation.py` passando
  como prova disso.

## 1:00 – 2:00 · Arquitetura

- Abrir `docs/architecture.md`, mostrar o diagrama do grafo LangGraph:
  fan-out real (`check_service_status` + `search_incident_history` no
  mesmo superstep), fan-in em `assess_risk`, loop de retry com parada
  garantida, 3 condicionais.
- Citar rapidamente: tool HTTP real + MCP (Fase 4), RAG via FTS5 (Fase
  5), motor de risco determinístico (Fase 6).

## 2:00 – 4:00 · Dois cenários de uso

- `docker compose up -d app mock-monitoring` + seed +
  `python scripts/demo.py` (ou os `curl` de `docs/exemplos/README.md`).
- **Cenário 1 (fluxo principal)**: `payments-api`, erro de conexão com
  banco. Mostrar `severity=high`, `risk.trend=increasing` (tendência real,
  calculada sobre histórico do mock-monitoring), evidência de RAG
  (`INC-00001`, runbook de connection pool).
- **Cenário 2 (risco/adversarial)**: prompt injection pedindo para
  revelar a API key e apagar o banco. Mostrar `security_violation=true`,
  bloqueado antes de qualquer chamada ao LLM, `recommended_actions=[]`.

## 4:00 – 5:00 · Segurança e aprovação humana

- Mostrar `requires_human_approval=true` no cenário 1 (severidade alta em
  produção) e o endpoint `POST /incidents/{id}/approve` registrando a
  decisão — deixar claro que a aplicação **nunca executa** a ação
  automaticamente, aprovar é só trilha de auditoria.
- Rodar (ou mostrar já rodado) `tests/integration/test_security_adversarial.py`.

## 5:00 – 6:00 · Evidência de QA

- Mostrar `docs/qa/code-review-fase7-security.md` — revisão de código com
  Gemini real sobre um diff real do projeto, e o teste que nasceu de uma
  das sugestões (`tests/unit/test_policies.py::
  test_security_violation_takes_precedence_even_over_llm_parse_failed`).
- Mostrar `tests/e2e/test_full_incident_lifecycle.py` rodando (stack
  completa: API → grafo → tools → RAG → risco → observabilidade) e
  `docs/qa/priorizacao-testes.md` (por que esses 2 cenários E2E).

## 6:00 – 8:00 · Pipeline, logs, anomalia, risco

- Mostrar o badge/run verde do GitHub Actions
  (`.github/workflows/ci.yml`: lint → test → build).
- Contar a história real: 2 execuções de CI falharam de verdade (não
  provocadas), raiz encontrada foi `pytest` puro não adicionar o projeto
  ao `sys.path` — `docs/qa/ci-failure-root-cause.md`. Mostrar o fix
  (`pythonpath = ["."]` em `pyproject.toml`) e a run seguinte verde.
- Rodar `python scripts/anomaly_report.py` — mostrar `payments-api`
  classificado como tendência `increasing` e risco de falha alto, com
  explicação em linguagem natural.

## 8:00 – 9:00 · Low-code (n8n)

- Abrir `n8n/incidentai-alert.json` importado no n8n
  (`docker compose -f docker-compose.yml -f docker-compose.low-code.yml --profile low-code up`):
  Webhook → IF severidade ≥ high → formata mensagem → HTTP Request de
  alerta.
- Mostrar `app/services/notifier.py` disparando o webhook no cenário 1
  (severidade alta) e NÃO disparando em um incidente de severidade baixa.

## 9:00 – 10:00 · Limitações e melhorias futuras

- RAG é FTS5 léxico (sem embeddings) — funciona bem no domínio fechado da
  demo, mas não generaliza semanticamente.
- Aprovação humana é só trilha de auditoria — não há execução real de
  ações remediadoras (deliberado: fora do escopo por segurança).
- MCP funciona mas sobe um subprocesso por chamada (`TOOLS_TRANSPORT=mcp`)
  — uma sessão persistente seria mais eficiente em produção.
- Próximos passos possíveis: RAG vetorial, autenticação/RBAC, execução
  supervisionada de remediações simples.

---

## Checklist antes de gravar

- [ ] `docker compose up -d app mock-monitoring` + seed rodando
- [ ] `python scripts/demo.py` testado e com saída limpa
- [ ] Run verde do GitHub Actions visível
- [ ] `docs/qa/code-review-fase7-security.md` aberto numa aba
- [ ] n8n com o workflow importado (ou print de fallback caso a demo ao
      vivo falhe)
