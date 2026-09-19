# Priorização de testes por risco/impacto

> Critério 12 do enunciado: "selecionar e justificar pelo menos um teste
> ou cenário considerado prioritário com base em risco, impacto ou
> criticidade". Este documento cobre os cenários E2E (o nível mais caro
> de manter, então o que mais precisa de justificativa) e resume a lógica
> usada nas demais camadas da pirâmide.

## Metodologia

Cada cenário candidato foi avaliado em três eixos:

1. **Cobertura de componentes não-triviais por teste** — um E2E é caro
   (mais lento, mais frágil a mudanças); só compensa quando exercita
   várias partes do sistema que só funcionam corretamente **juntas**
   (contrato entre módulos), não coisas já bem cobertas isoladamente.
2. **Probabilidade de regressão silenciosa** — mudanças em `app/risk/`,
   `app/tools/`, `app/memory/` podem quebrar a integração entre eles sem
   quebrar nenhum teste unitário isolado (cada um mocka a interface do
   vizinho).
3. **Custo de um bug chegar em produção sem ser pego** — para este
   domínio (copiloto de SRE), o pior cenário é responder com confiança
   alta durante uma falha real do próprio sistema de observabilidade.

## E2E escolhidos (tests/e2e/test_full_incident_lifecycle.py)

### 1. `test_payments_api_high_risk_scenario_full_stack` — prioridade alta

**Por quê este e não outro "caminho feliz"?** É o único cenário que
exercita, na mesma execução, os 5 componentes que só têm valor quando
compõem corretamente: tool HTTP real (histórico genuíno, não mockado) →
motor de risco (`classify_trend` sobre uma série real, não fabricada no
teste) → RAG (FTS5 sobre dados reais) → LLM (categorização) →
observabilidade (auditoria correlacionada). Um bug de contrato entre
`check_service_status` e `assess_risk` (ex.: nome de campo errado em
`error_rate_series`) não apareceria em nenhum teste unitário — cada lado
mocka a interface do outro. Esse é exatamente o tipo de regressão que só
um E2E pega.

**Risco se não existisse**: severidade calculada errada silenciosamente
(ex.: sempre "low" porque o histórico nunca chega em `assess_risk`) é o
pior tipo de bug possível neste domínio — o sistema erraria com
confiança, não travaria.

### 2. `test_monitoring_down_degrades_gracefully_full_stack` — prioridade alta

**Por quê**: é o cenário de risco/falha exigido pelo enunciado (item 4.1)
E o que teria o maior custo de regressão silenciosa. Três degradações
diferentes precisam compor sem se cancelar: tool HTTP falha (500) →
fallback (`status=unknown`) → motor de risco **não pode** interpretar
ausência de dado como risco alto (`app/risk/anomaly.py`, peso brando para
`status=unknown`) → resposta ainda assim é 200 com todos os campos
válidos. Qualquer um desses três elos quebrado sozinho (ex.: alguém
"corrige" o peso de `unknown` para ficar igual a `down`, achando que é
mais seguro) muda o comportamento de segurança do sistema de forma
sutil — é fácil justificar a mudança isoladamente e só um teste que
força o cenário de ponta a ponta pega a consequência real.

## Resumo da priorização nas outras camadas

- **Unit**: prioriza módulos determinísticos com muitas bordas
  (`app/risk/anomaly.py`, `app/memory/rag.py`, `app/security/guardrails.py`)
  — bugs aqui são silenciosos por natureza (não lançam exceção, só
  calculam errado).
- **Integration**: prioriza o contrato entre camadas adjacentes
  (cliente HTTP ↔ mock-monitoring; grafo ↔ tools; grafo ↔ RAG) e os dois
  testes de regressão estrutural do LangGraph (paralelismo real,
  `InvalidUpdateError` por reducer ausente) — são armadilhas específicas
  desta arquitetura, documentadas em `app/agent/state.py`.
- **Adversarial** (`tests/integration/test_security_adversarial.py`):
  prioridade máxima por definição regulatória do enunciado (item 4.5) —
  independente de custo/benefício técnico, é um requisito não-negociável.
