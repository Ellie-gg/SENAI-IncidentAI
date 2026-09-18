# Disk Capacity Runbook

## No Space Left on Device

Esse erro derruba qualquer processo que tente escrever no volume afetado
(logs, banco de dados, arquivos temporários), então o impacto costuma ser
abrupto e afetar múltiplos componentes ao mesmo tempo.

### Causas Comuns

- Logs sem rotação configurada, acumulando indefinidamente.
- Arquivos temporários de jobs batch que falharam sem limpar depois.
- Crescimento orgânico do banco de dados sem alerta de capacidade
  configurado.

## Mitigação Imediata

1. Identificar os maiores consumidores de espaço no volume
   (`du -sh` por diretório).
2. Rotacionar/comprimir/remover logs antigos com segurança (nunca remover
   logs que ainda não foram exportados para o sistema de observabilidade).
3. Se for banco de dados, considerar expansão de volume antes de tentar
   liberar espaço manualmente — é mais seguro.

## Prevenção

Alertar em 80% de uso de disco, não em 100%. Rotação de log automática
(logrotate ou equivalente) deveria ser padrão em todo serviço que escreve
log em arquivo.
