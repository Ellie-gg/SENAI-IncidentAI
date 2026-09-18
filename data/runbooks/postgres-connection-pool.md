# Postgres Runbook

Guia de triagem para incidentes de conectividade com o banco de dados
Postgres em produção.

## Connection Pool

### Exhaustion

Quando o número de conexões ativas se aproxima do `max_size` configurado
no pool, novas requisições começam a falhar com timeout de conexão. Os
sintomas típicos nos logs são `connection pool exhausted` e
`database connection timeout`.

Passos de triagem:
1. Verifique o número de conexões ativas vs. `max_size` configurado.
2. Compare com o tráfego recente — um pico de tráfego sem aumento
   proporcional do pool é a causa mais comum.
3. Verifique se há queries lentas segurando conexões por muito tempo
   (`pg_stat_activity`).

Mitigação: aumentar `max_size` temporariamente e considerar adicionar
PgBouncer como pooler externo para absorver picos.

### Connection Reset

Conexões resetadas (`connection reset by peer`) frequentemente indicam
jobs abrindo e fechando conexões em alta frequência (ex.: um loop que abre
uma conexão nova por linha processada). A correção estrutural é reusar uma
única conexão pooled durante todo o job.

## Réplicas de Leitura

Se o serviço usa réplicas de leitura, um lag de replicação alto pode
mascarar um problema de conectividade como inconsistência de dados. Vale
checar o lag antes de assumir que o problema é só de conexão.
