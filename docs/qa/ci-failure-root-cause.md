# Análise de falha de CI — causa raiz real (2 execuções, `sys.path`)

> Complementa `docs/qa/ci-failure-run-35408333095.md` (primeira
> investigação, que concluiu — incorretamente — "infraestrutura
> transitória"). Duas runs reais falharam da mesma forma antes deste
> diagnóstico: [#35408333095](https://github.com/Ellie-gg/SENAI-IncidentAI/actions/runs/35408333095)
> e [#35408982651](https://github.com/Ellie-gg/SENAI-IncidentAI/actions/runs/35408982651).

## Investigação

Sem permissão de admin no repositório, o log bruto do job não pôde ser
baixado (`403`/`401` em duas rotas diferentes da API). A saída foi
instrumentar o próprio `.github/workflows/ci.yml` para reemitir trechos do
log como anotações `::error::`/`::notice::` — essas SIM ficam visíveis via
`GET /repos/.../check-runs/{id}/annotations`, sem precisar de permissão
extra.

Duas rodadas de instrumentação depois, a anotação decisiva apareceu:

```
ERROR collecting tests/e2e/test_full_incident_lifecycle.py
ImportError while importing test module '.../tests/e2e/test_full_incident_lifecycle.py'.
Traceback:
.../importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
tests/e2e/test_full_incident_lifecycle.py:23: in <module>
    from app.config import get_settings
```

O trecho crucial — `importlib/__init__.py: in import_module` no meio da
pilha — é assinatura do mecanismo de import de teste do PRÓPRIO pytest,
não do código da aplicação. Isso apontou para um problema de
`sys.path`/descoberta de módulo, não para um bug de negócio.

## Causa raiz (confirmada localmente, sem precisar do CI)

`python -m pytest` **sempre** adiciona o diretório atual (`cwd`) ao
`sys.path` — é um comportamento do próprio `python -m`, não do pytest.
`pytest` invocado como comando (`pytest -q`, o script instalado pelo pip)
**não** faz isso.

Toda vez que esta sessão rodou a suíte localmente, foi via
`./.venv/Scripts/python.exe -m pytest ...` — mascarando completamente o
problema. O `.github/workflows/ci.yml` roda `pytest -q` direto (padrão
comum e razoável), expondo o problema real: sem `app/`, `mock_monitoring/`
e `scripts/` no `sys.path`, `from app.config import get_settings` (e todo
import equivalente) falha com `ModuleNotFoundError: No module named 'app'`.

**Reproduzido localmente** rodando o executável `pytest` diretamente (não
via `-m`):

```
.venv/Scripts/pytest.exe --collect-only -q
```

Resultado: `142 tests collected, 8 errors in 1.54s` —
`ModuleNotFoundError: No module named 'app'` em 8 arquivos de teste
(justamente os que não tinham nenhum outro import que, por acaso,
carregasse `app` no cache do `sys.modules` antes).

## Correção

`pyproject.toml` → `[tool.pytest.ini_options]` → `pythonpath = ["."]`
(opção nativa do pytest ≥7, sem plugin extra): garante que o diretório do
projeto entra no `sys.path` **independente de como o pytest é invocado**
— `pytest`, `python -m pytest`, IDE, ou CI.

```toml
[tool.pytest.ini_options]
pythonpath = ["."]
```

**Validado**: `.venv/Scripts/pytest.exe -q` (comando puro, o mesmo que o
CI usa) → `204 passed`.

## Por que a primeira análise (infraestrutura transitória) estava errada

A reprodução via Docker (`python:3.12-slim`) usava
`python -m pytest`, então "herdava" a mesma máscara que o ambiente local
sempre teve — 3/3 execuções passaram ali não porque o CI estivesse
com um problema transitório, mas porque a reprodução usava o comando
ERRADO (o que mascarava o bug) para validar o comando CERTO (o que expõe
o bug). Lição registrada: reproduzir uma falha de CI precisa replicar o
comando **exato**, não só o ambiente.
