"""Explica logs de pipeline com IA — pelo menos 2 etapas (lint, testes,
build, Dockerfile, CI, deploy) por execução, conforme o enunciado.

Usa o mesmo `get_llm()`/`LLM_PROVIDER` do resto da aplicação. Uso típico:
capturar a saída real de cada etapa (localmente ou de um log do CI
baixado) e passar aqui.

    ruff check . > /tmp/lint.log 2>&1
    pytest -q > /tmp/test.log 2>&1
    python scripts/ai_log_analysis.py \\
        --stage lint=/tmp/lint.log \\
        --stage test=/tmp/test.log \\
        --out docs/qa/ci-failure-lint-test.md
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.llm import get_llm  # noqa: E402

STAGE_PROMPT_TEMPLATE = """Você é um engenheiro de DevOps sênior analisando a saída bruta de uma \
etapa de pipeline CI/CD chamada "{stage}", de um projeto Python \
(FastAPI + LangGraph). Escreva a análise em Markdown com estas seções:

## O que esta etapa faz
(1 frase)

## Resultado
(sucesso ou falha — diga explicitamente, com a evidência do log que sustenta a conclusão)

## Causa raiz e correção sugerida
(se falhou: aponte a causa raiz mais provável E uma correção concreta, \
citando o trecho exato do log que embasa o diagnóstico. Se passou: aponte \
algo notável mesmo assim — warning, lentidão, flakiness — ou diga "nada \
notável" explicitamente.)

## Log bruto
```
{log}
```
"""

MAX_LOG_CHARS = 20_000


async def analyze_stage(stage: str, log_text: str) -> str:
    client = get_llm()
    if len(log_text) > MAX_LOG_CHARS:
        # mantém o FINAL do log — é onde o erro normalmente aparece
        log_text = "... (log truncado, mostrando o final)\n" + log_text[-MAX_LOG_CHARS:]
    prompt = STAGE_PROMPT_TEMPLATE.format(stage=stage, log=log_text)
    return await client.raw_text(prompt)


async def run(stages: list[tuple[str, Path]]) -> str:
    sections = []
    for name, path in stages:
        log_text = path.read_text(encoding="utf-8", errors="replace")
        analysis = await analyze_stage(name, log_text)
        sections.append(f"## Etapa: `{name}`\n\n{analysis}\n")

    header = (
        f"# Análise de logs de pipeline (IA)\n\n"
        f"Gerado em {datetime.now(UTC).isoformat()} | etapas analisadas: "
        f"{', '.join(name for name, _ in stages)}\n\n---\n\n"
    )
    return header + "\n".join(sections)


def _parse_stage(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError(f"formato esperado NOME=CAMINHO, recebido: {value!r}")
    name, path = value.split("=", 1)
    return name, Path(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Explica logs de pipeline com IA.")
    parser.add_argument(
        "--stage",
        action="append",
        type=_parse_stage,
        required=True,
        metavar="NOME=CAMINHO",
        help="Pode ser passado múltiplas vezes (mínimo 2 para o critério do enunciado).",
    )
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    report = asyncio.run(run(args.stage))

    if args.out:
        out_path = Path(args.out)
    else:
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        out_path = (
            Path(__file__).resolve().parent.parent / "docs" / "qa" / f"ci-log-analysis-{stamp}.md"
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(f"Análise salva em {out_path}")


if __name__ == "__main__":
    main()
