# Ciclo de refinamento documentado

> Critério 15 do enunciado. Dois refinamentos reais, feitos durante o
> desenvolvimento (não reconstruídos depois) — cada um com o problema
> observado, a mudança e o resultado medido.

## 1. Reordenação do grafo: `approval_check` via `generate_recommendation`

**Quando**: Fase 7 (`feature/security`), ao implementar `policies.py`.

**Problema observado**: o grafo desenhado na Fase 3 rodava
`assess_risk → approval_check → generate_recommendation`. Para classificar
a ação como `READ`/`RECOMMEND`/`CHANGE`/`DELETE`
(`app/security/policies.py::classify_action`), `approval_check` precisava
da lista de ações *recomendadas* — mas essa lista só existe depois de
`generate_recommendation` rodar, que rodava *depois* dele. Na prática,
`approval_check` só tinha acesso a `key_signals`/`probable_cause` (saída
de `analyze_incident`) como proxy, o que é impreciso: a causa provável de
um incidente não diz o que o sistema vai efetivamente recomendar. Efeito
colateral pior: um incidente que caía em `needs_approval` terminava em
`finalize_pending_approval → END` sem nunca chamar
`generate_recommendation` — a pessoa aprovando via `/approve` não via
*nenhuma* ação sugerida, só que precisava aprovar algo indefinido.

**Mudança**: reordenado para
`assess_risk → [retry|recommend] → generate_recommendation →
approval_check → [needs_approval|auto]`. A decisão de retry (que antes
vivia em `route_after_approval`) foi movida para logo depois de
`assess_risk` (`route_after_risk`), porque não faz sentido gastar uma
chamada de LLM gerando recomendação para uma análise que ainda vai ser
refeita.

**Resultado**: `approval_check` agora classifica a ação REAL
(`app/agent/nodes.py::approval_check`, usa `state["recommended_actions"]`
de verdade). Um incidente pendente de aprovação chega em `/approve` com
`action_class` e as ações já visíveis na resposta anterior — a pessoa
aprovando sabe o que está aprovando. Coberto por
`tests/unit/test_routing.py` (a nova divisão `route_after_risk`/
`route_after_approval`) e `tests/integration/test_approve_endpoint.py`.
Diagrama atualizado em `docs/architecture.md`.

## 2. Blocklist de guardrails: falso positivo em "restart production"

**Quando**: Fase 7, escrevendo `tests/integration/test_security_adversarial.py`.

**Problema observado**: a blocklist inicial de `app/security/guardrails.py`
incluía a frase literal `"restart production"` como padrão bloqueado,
pensando em comandos destrutivos. Ao escrever o teste
`test_destructive_action_keywords_never_auto_execute_and_require_approval`
com uma descrição perfeitamente legítima — *"Service is unresponsive, may
need a restart production to recover"* — o teste falhou:
`security_violation=True`. A blocklist estava bloqueando uma descrição de
incidente real, não uma tentativa de injeção. O mesmo aconteceu, de
forma mais grave, num teste separado que verificava aprovação humana via
`LLM_PROVIDER=mock_fail`: o incidente inteiro era bloqueado antes mesmo de
chegar no LLM.

**Mudança**: removida a frase `"restart production"` (e qualquer padrão
em linguagem natural) da blocklist. A blocklist ficou restrita a (a)
meta-instruções clássicas de prompt injection (`"ignore previous
instructions"`, `"show api key"`, `"you are now"` etc.) e (b) sintaxe de
comando inequivocamente destrutiva (`kubectl delete`, `terraform destroy`,
`rm -rf`, `drop table` — coisas que ninguém escreve numa descrição de
incidente em prosa). O controle correto para "pedir para reiniciar
produção" não é bloquear a análise, é `app/security/policies.py::
requires_approval` (`CHANGE` em produção exige aprovação humana) — camada
diferente, já existente.

**Resultado**: os dois testes passaram a refletir o comportamento
pretendido (`security_violation=False` para a descrição legítima,
`requires_human_approval=True` quando a ação é de fato `CHANGE` em
produção). Adicionado um teste de regressão dedicado
(`tests/unit/test_guardrails.py::
test_find_blocked_patterns_does_not_false_positive_on_legitimate_ops_language`)
para este caso específico não voltar.

---

Um terceiro caso, menor mas real, está documentado em
`docs/qa/ci-failure-root-cause.md`: um bug de `sys.path` que só aparecia
rodando `pytest` puro (não `python -m pytest`) — encontrado através de
falhas reais e não provocadas do pipeline de CI, não de um teste
local.
