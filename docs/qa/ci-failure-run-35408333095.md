# Análise de falha de CI — run #35408333095 (IA)

> **Atualização**: a causa raiz REAL foi encontrada depois (2 runs
> adicionais, ver `docs/qa/ci-failure-root-cause.md`) — não era
> infraestrutura transitória como concluído abaixo, era `sys.path`. Este
> documento fica como registro do processo de investigação (inclusive o
> caminho errado), o outro tem o diagnóstico e fix corretos.


> Gerado manualmente pelo agente de IA que conduziu esta implementação
> (não pelo script `scripts/ai_log_analysis.py`, que também está pronto e
> testado mecanicamente — ver nota no fim). Cobre 2 etapas do pipeline
> (`lint` e `test`), conforme o critério do enunciado.
>
> Run: <https://github.com/Ellie-gg/SENAI-IncidentAI/actions/runs/35408333095>
> (branch `develop`, primeiro push do `.github/workflows/ci.yml`)

## Etapa: `lint (ruff)`

**Resultado**: sucesso. `ruff check .` e `ruff format --check .` passaram
sem nenhum apontamento, em 24s de execução (incluindo `pip install`).
Nada notável.

## Etapa: `test (pytest)`

**Resultado**: falha. `Process completed with exit code 2.`

### Evidência coletada

O download do log bruto via API retornou `403 Must have admin rights to
Repository` (limitação real deste ambiente — a sessão não tem token de
API com permissão de admin sobre o repositório, só leitura pública via
`GET /repos/.../actions/runs`). Diante disso, a investigação seguiu por
sinais indiretos, todos obtidos via API pública:

- **Timing anômalo**: o step `Run pytest -q --junitxml=pytest-results.xml`
  levou apenas **2 segundos** (`00:09:35Z` → `00:09:37Z`). A suíte tem 189
  testes e, rodando localmente (mesmo hardware, mesma suíte), leva entre
  8 e 12 segundos — incluindo um teste que sobe um subprocesso MCP real e
  sozinho leva ~5s. Dois segundos é tempo insuficiente para sequer
  terminar a coleta dos módulos de teste, quanto mais executá-los.
- **Exit code 2**: no pytest, isso normalmente indica interrupção da
  execução (não uma falha de asserção comum, que seria exit code 1).
  Combinado com o timing acima, aponta mais para uma interrupção do
  processo (preempção do runner, falha de rede durante import, timeout
  interno do GitHub Actions) do que para um teste quebrado de verdade.
- **`lint` e `test` usam o mesmo `pip install -r requirements.txt`** e o
  `lint` completou normal — reduz a chance de ser problema de resolução
  de dependência específico do ambiente Linux.

### Reprodução local (Docker, ambiente equivalente ao runner)

Para isolar se era um bug determinístico do código ou algo do ambiente,
reproduzi o mesmo comando do CI (`pip install -r requirements.txt` limpo
+ `pytest -q`) dentro de `python:3.12-slim` (mesma versão de Python do
workflow, dependências resolvidas do zero, sem cache local):

```
docker run --rm -v <repo>:/repo -w /repo python:3.12-slim bash -c "
  pip install -q -r requirements.txt
  LLM_PROVIDER=mock MONITORING_ENABLED=false python -m pytest -q
"
```

Resultado: **189 passed em 3 execuções consecutivas** (9.5s, 9.1s, 12.5s),
0 falhas, 0 flakiness observada.

## Conclusão

A evidência disponível (timing de 2s incompatível com o tamanho real da
suíte, exit code 2 característico de interrupção, e 3/3 reproduções
limpas num ambiente equivalente) aponta para **falha transitória de
infraestrutura do runner** (preempção, hiccup de rede durante
`pip install`/import, ou limite de tempo interno do Actions) — não para
um defeito determinístico no código ou nos testes. Não foi possível
confirmar a causa raiz exata porque o log bruto do job não estava
acessível com o nível de permissão desta sessão (limitação documentada,
não contornada).

**Ação tomada**: nenhuma mudança de código — o próximo push (Fase 10,
mesmo commit que adiciona esta análise) serve como nova tentativa
natural. Se o padrão se repetir em execuções futuras, os próximos passos
seriam: (1) adicionar `pytest-rerunfailures` com 1 retry automático no
job `test`, (2) revisar se algum teste depende de timing agressivo o
bastante para ser sensível a um runner sob carga (candidato:
`test_fanout_topology_runs_nodes_concurrently`, que assume overlap de
paralelismo dentro de uma margem de 0.17s).

---

*Nota: `scripts/ai_log_analysis.py` (adicionado nesta mesma fase) é o
mecanismo reutilizável para este tipo de análise — recebe os logs brutos
de N etapas e usa o LLM configurado (`GOOGLE_API_KEY` + `LLM_PROVIDER=gemini`
para uma análise real) para produzir exatamente este tipo de relatório.
Não foi usado para ESTE documento porque o log bruto da etapa `test` não
pôde ser baixado (403 acima) — a investigação usou os sinais indiretos
disponíveis pela API pública em vez do texto completo do log.*
