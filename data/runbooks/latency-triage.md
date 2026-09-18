# Latency Triage Runbook

Como investigar degradação de latência (p95/p99) em serviços HTTP.

## Diagnóstico Inicial

Compare a latência atual contra a baseline dos últimos 7 dias no mesmo
horário. Um aumento repentino e isolado (não gradual) costuma apontar para
um evento específico: deploy, mudança de tráfego, ou uma dependência
externa degradada.

### Dependências Downstream

A causa mais comum de degradação de latência em APIs orquestradoras é uma
chamada síncrona a um serviço downstream sem timeout configurado. Se o
downstream começa a responder devagar, a latência do serviço chamador
sobe proporcionalmente — às vezes multiplicando o efeito em cascata.

Verifique:
- Se todas as chamadas externas têm timeout explícito.
- Se existe circuit breaker configurado e se ele está abrindo.
- O dashboard de latência do serviço downstream especificamente.

## Mitigação

Timeout agressivo (ex.: 500ms) combinado com circuit breaker evita que uma
dependência lenta degrade o serviço inteiro. Fallback gracioso (resposta
parcial ou cache) é preferível a deixar a requisição pendurada.
