# Memory Pressure & OOM Runbook

## Identificando Memory Pressure

Sinais de alerta: uso de heap subindo de forma constante (não serrilhado,
como um garbage collector saudável costuma mostrar), ou pods sendo
`OOMKilled` pelo orquestrador.

### Padrões Comuns

- **Carregar dataset inteiro em memória**: jobs de export/import que
  carregam todo o resultado de uma query antes de processar, em vez de
  processar em streaming/paginado. É a causa mais comum de OOM em jobs
  batch.
- **Memory leak em cache não limitado**: um cache em memória sem TTL ou
  limite de tamanho cresce indefinidamente até estourar o limite do
  container.

## Mitigação Imediata

Um restart controlado alivia a pressão enquanto a causa raiz é
investigada, mas não é uma correção — o padrão vai se repetir. Para jobs
de export/import, a correção estrutural é processar em lotes (streaming)
em vez de carregar tudo de uma vez.

## Prevenção

Definir limites de memória realistas no orquestrador e alertar em 80% de
uso, antes do OOM acontecer.
