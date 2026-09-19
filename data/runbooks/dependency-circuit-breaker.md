# Dependência Externa Degradada — Runbook

## Diagnóstico

Quando uma dependência externa (provedor de e-mail, gateway de pagamento,
serviço de terceiros) degrada, o sintoma no serviço chamador costuma ser
fila crescente, retries acumulando, ou timeouts em cascata.

### Verificações

1. Status page público do provedor, se existir.
2. Taxa de erro específica das chamadas para aquela dependência (não a
   taxa de erro geral do serviço).
3. Se o circuit breaker está configurado e se chegou a abrir.

## Mitigação

- **Fallback**: se existir um provedor secundário, ativá-lo reduz o
  impacto imediato.
- **Dead-letter queue**: para operações assíncronas (ex.: envio de
  e-mail), enfileirar as falhas para reprocessamento evita perda de dados
  enquanto a dependência está fora.
- **Circuit breaker**: parar de tentar a dependência degradada por um
  período evita que os retries piorem ainda mais a situação dela (e
  liberam recursos do próprio serviço chamador).

## Depois que a Dependência Volta

Reprocessar a dead-letter queue de forma controlada (não tudo de uma vez)
evita gerar um novo pico de carga logo na recuperação.
