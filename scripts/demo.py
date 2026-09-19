"""Roda os dois cenários de uso exigidos (fluxo principal + risco/
adversarial) contra uma instância já no ar do IncidentAI, imprimindo o
resultado de forma legível. Usado na gravação do vídeo de demonstração.

Pré-requisitos:
    docker compose up -d app mock-monitoring
    docker compose exec app python scripts/seed_incidents.py

Uso:
    python scripts/demo.py
    python scripts/demo.py --base-url http://localhost:8000
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "docs" / "exemplos"

SCENARIOS = [
    ("Cenário 1 — Fluxo principal", "cenario-1-fluxo-principal.json"),
    ("Cenário 2 — Risco / adversarial", "cenario-2-risco-adversarial.json"),
]


def _print_header(title: str) -> None:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def _print_summary(body: dict) -> None:
    print(f"incident_id:            {body.get('incident_id')}")
    print(f"trace_id:                {body.get('trace_id')}")
    print(f"category:                {body.get('category')}")
    print(f"severity:                {body.get('severity')}")
    print(f"confidence:              {body.get('confidence')}")
    risk = body.get("risk", {})
    print(f"risk.score / trend:      {risk.get('score')} / {risk.get('trend')}")
    print(f"failure_risk:            {risk.get('failure_risk')}")
    print(f"action_class:            {body.get('action_class')}")
    print(f"requires_human_approval: {body.get('requires_human_approval')}")
    print(f"security_violation:      {body.get('security_violation')}")
    print(f"terminal_reason:         {body.get('terminal_reason')}")
    print("recommended_actions:")
    for action in body.get("recommended_actions", []):
        print(f"  - {action}")
    evidence = body.get("evidence", {})
    print(f"evidence.similar_incidents: {evidence.get('similar_incidents')}")
    print(f"evidence.runbooks:          {evidence.get('runbooks')}")
    print(
        f"evidence.service_status:    {evidence.get('service_status')} "
        f"(source={evidence.get('monitoring_source')})"
    )


def run(base_url: str) -> int:
    health_ok = False
    try:
        r = httpx.get(f"{base_url}/health", timeout=5.0)
        health_ok = r.status_code == 200
    except httpx.HTTPError:
        pass
    if not health_ok:
        print(f"ERRO: {base_url}/health não respondeu. Suba a app primeiro:")
        print("  docker compose up -d app mock-monitoring")
        return 1

    for title, filename in SCENARIOS:
        payload = json.loads((EXAMPLES_DIR / filename).read_text(encoding="utf-8"))
        _print_header(title)
        print(f"POST /incidents/analyze  ({filename})")
        r = httpx.post(f"{base_url}/incidents/analyze", json=payload, timeout=30.0)
        print(f"HTTP {r.status_code}\n")
        _print_summary(r.json())

    print("\n" + "=" * 70)
    print("Demo concluída.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Demo dos 2 cenários do IncidentAI.")
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()
    sys.exit(run(args.base_url))


if __name__ == "__main__":
    main()
