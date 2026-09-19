"""Revisão de código com IA sobre um diff real do projeto (item 4.7 /
critério 12 do enunciado).

Usa o mesmo `get_llm()`/`LLM_PROVIDER` do resto da aplicação:
- `LLM_PROVIDER=mock` (default): produz uma saída mecânica, sem chamada
  externa — útil para validar o script (extração de diff, formatação,
  escrita do arquivo), mas NÃO é uma revisão de verdade.
- `LLM_PROVIDER=gemini` + `GOOGLE_API_KEY`: gera a revisão real com o
  modelo configurado em `LLM_MODEL`.

Uso:
    python scripts/ai_code_review.py --base develop --head feature/security
    python scripts/ai_code_review.py --base develop --head HEAD --out docs/qa/code-review-custom.md
"""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.services.llm import get_llm  # noqa: E402

REVIEW_PROMPT_TEMPLATE = """Você é um revisor de código sênior revisando uma mudança real de um \
projeto Python (FastAPI + LangGraph, agente de SRE/DevOps). Analise o \
diff abaixo e produza uma revisão objetiva em Markdown com estas seções:

## Resumo
(1-2 frases sobre o que a mudança faz)

## Problemas encontrados
(lista priorizada por risco/impacto: correção > segurança > design > \
estilo; para cada item, aponte o arquivo/trecho e sugira uma correção \
concreta. Se não houver problema relevante, diga isso explicitamente em \
vez de inventar um.)

## Pontos positivos
(o que a mudança faz bem — seja específico, não genérico)

## Sugestões de teste
(cenários de teste que faltam ou deveriam ser priorizados, com \
justificativa de risco/impacto para cada um)

Cite trechos concretos do diff nas suas observações.

## Diff
```diff
{diff}
```
"""

MAX_DIFF_CHARS = 60_000


def get_diff(base: str, head: str) -> str:
    # encoding="utf-8" explícito: no Windows, subprocess.run(text=True) usa
    # o codepage do console (cp1252 aqui) por padrão, que não decodifica
    # acentos do diff (mensagens de commit/comentários em português) — sem
    # isso o subprocess crasha e get_diff silenciosamente devolveria None.
    result = subprocess.run(  # noqa: S603
        ["git", "diff", f"{base}...{head}", "--", ".", ":(exclude)*.md"],  # noqa: S607
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
        cwd=Path(__file__).resolve().parent.parent,
    )
    return result.stdout


async def run_review(base: str, head: str) -> str:
    diff = get_diff(base, head)
    if not diff.strip():
        return f"# Code Review — {head} vs {base}\n\nNenhuma diferença encontrada.\n"

    truncated = len(diff) > MAX_DIFF_CHARS
    if truncated:
        diff = diff[:MAX_DIFF_CHARS]

    client = get_llm()
    prompt = REVIEW_PROMPT_TEMPLATE.format(diff=diff)
    review_text = await client.raw_text(prompt)

    settings = get_settings()
    header = (
        f"# Code Review — `{head}` vs `{base}`\n\n"
        f"- Gerado em: {datetime.now(UTC).isoformat()}\n"
        f"- LLM_PROVIDER: `{settings.llm_provider}` "
        f"(modelo: `{settings.llm_model}`)\n"
        + ("- ⚠️ diff truncado em 60.000 caracteres\n" if truncated else "")
        + "\n---\n\n"
    )
    return header + review_text


def main() -> None:
    parser = argparse.ArgumentParser(description="Revisão de código com IA sobre um diff real.")
    parser.add_argument("--base", default="develop")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    review = asyncio.run(run_review(args.base, args.head))

    if args.out:
        out_path = Path(args.out)
    else:
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        out_path = (
            Path(__file__).resolve().parent.parent / "docs" / "qa" / f"code-review-{stamp}.md"
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(review, encoding="utf-8")
    print(f"Revisão salva em {out_path}")


if __name__ == "__main__":
    main()
