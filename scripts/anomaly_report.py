"""Detecção de anomalia + estimativa de tendência/risco, com explicação
por IA (item 4.8 / critério 13 do enunciado).

Usa dados REAIS do projeto: os cenários de série temporal definidos em
`mock_monitoring/main.py` (os mesmos que a demo, os testes E2E e o
container de monitoramento usam) — não são fabricados só para este
script. O cálculo de tendência/risco é 100% determinístico
(`app/risk/anomaly.py`, já testado em tests/unit/test_anomaly.py); a IA
entra só na camada de EXPLICAÇÃO em linguagem natural.

Uso:
    python scripts/anomaly_report.py
    python scripts/anomaly_report.py --out docs/evidencias/anomaly-custom.md
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.risk.anomaly import classify_failure_risk, classify_trend, failure_risk  # noqa: E402
from app.risk.scoring import classify_severity, compute_risk_score  # noqa: E402
from app.services.llm import get_llm  # noqa: E402
from mock_monitoring.main import _DEFAULT_SCENARIO, _SCENARIOS  # noqa: E402

EXPLAIN_PROMPT = """Você é um SRE sênior explicando uma anomalia operacional pro time de plantão, \
em português, para uma pessoa não-técnica do plantão (sem jargão desnecessário).

Dados observados para o serviço "{service}":
- Status atual: {status}
- Série de error rate (últimas {n} janelas, mais antiga primeiro): {error_series}
- Latência p95 atual: {latency}ms
- Tendência calculada (regressão linear normalizada): {trend_label} \
(inclinação relativa={rel_slope:.3f}, confiança={confidence:.2f})
- Probabilidade estimada de falha: {failure_p:.1%} ({failure_label})
- Score de risco determinístico: {risk_score} (severidade: {severity})

Escreva uma explicação curta (4 a 6 frases): o que está acontecendo, por \
que foi classificado como {trend_label}/{severity}, e o que isso sugere \
fazer a seguir. Seja direto e específico aos números acima.
"""


async def analyze_service(service: str, scenario: dict) -> dict:
    error_series = scenario["error_rate_series"]
    latency_series = scenario["latency_series"]
    status = scenario["status"]

    trend = classify_trend(error_series)
    p = failure_risk(
        trend=trend,
        current_error_rate=error_series[-1],
        latency_p95_ms=latency_series[-1],
        status=status,
        environment="production",
    )
    failure_label = classify_failure_risk(p)
    score = compute_risk_score(
        environment="production",
        error_rate=error_series[-1],
        latency_p95_ms=latency_series[-1],
        status=status,
        trend_label=trend.label,
    )
    severity = classify_severity(score)

    client = get_llm()
    prompt = EXPLAIN_PROMPT.format(
        service=service,
        status=status,
        n=len(error_series),
        error_series=error_series,
        latency=latency_series[-1],
        trend_label=trend.label,
        rel_slope=trend.rel_slope,
        confidence=trend.confidence,
        failure_p=p,
        failure_label=failure_label,
        risk_score=score,
        severity=severity,
    )
    explanation = (await client.raw_text(prompt)).strip()

    return {
        "service": service,
        "status": status,
        "trend": trend.label,
        "rel_slope": round(trend.rel_slope, 4),
        "trend_confidence": trend.confidence,
        "failure_risk": p,
        "failure_risk_label": failure_label,
        "risk_score": score,
        "severity": severity,
        "explanation": explanation,
    }


def _is_anomalous(result: dict) -> bool:
    return result["trend"] == "increasing" or result["severity"] in ("high", "critical")


async def run() -> str:
    scenarios = dict(_SCENARIOS)
    scenarios.setdefault("_default_scenario_example", _DEFAULT_SCENARIO)

    results = [await analyze_service(service, scenario) for service, scenario in scenarios.items()]
    anomalies = [r for r in results if _is_anomalous(r)]

    lines = [
        f"# Relatório de anomalia e risco — {datetime.now(UTC).isoformat()}\n",
        f"**{len(anomalies)} de {len(results)} serviços monitorados apresentam "
        f"anomalia ou risco elevado.**\n",
    ]
    for r in results:
        flag = "🔴" if _is_anomalous(r) else "🟢"
        lines.append(f"## {flag} `{r['service']}`\n")
        lines.append(
            f"- Status: `{r['status']}` | Severidade: `{r['severity']}` "
            f"| Score de risco: `{r['risk_score']}`"
        )
        lines.append(
            f"- Tendência: `{r['trend']}` (inclinação relativa={r['rel_slope']}, "
            f"confiança={r['trend_confidence']})"
        )
        lines.append(
            f"- Risco de falha estimado: **{r['failure_risk']:.1%}** ({r['failure_risk_label']})\n"
        )
        lines.append(f"{r['explanation']}\n")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Relatório de anomalia/risco com explicação de IA."
    )
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    report = asyncio.run(run())

    if args.out:
        out_path = Path(args.out)
    else:
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        out_path = (
            Path(__file__).resolve().parent.parent
            / "docs"
            / "evidencias"
            / f"anomaly-report-{stamp}.md"
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(f"Relatório salvo em {out_path}")


if __name__ == "__main__":
    main()
