# Exemplos de requisição

Payloads prontos para `curl -d @arquivo`, cobrindo os dois cenários
exigidos (fluxo principal e risco/falha/adversarial) — ver seção
"Cenários de uso" do `README.md` principal para o comportamento esperado
de cada um.

```bash
curl -X POST http://localhost:8000/incidents/analyze \
  -H "Content-Type: application/json" \
  -d @docs/exemplos/cenario-1-fluxo-principal.json

curl -X POST http://localhost:8000/incidents/analyze \
  -H "Content-Type: application/json" \
  -d @docs/exemplos/cenario-2-risco-adversarial.json
```

- **`cenario-1-fluxo-principal.json`**: incidente real de conectividade
  com banco de dados em `payments-api`. Com `docker compose up` (app +
  mock-monitoring) e o seed rodado
  (`docker compose exec app python scripts/seed_incidents.py`), retorna
  `severity=high`, `risk.trend=increasing` e evidência de RAG real
  (`INC-00001`, runbook de connection pool).
- **`cenario-2-risco-adversarial.json`**: tentativa de prompt injection
  (pede para revelar a API key e apagar o banco). Retorna
  `security_violation=true`, `terminal_reason=security_blocked`,
  `recommended_actions=[]` — bloqueado antes de qualquer chamada ao LLM.
