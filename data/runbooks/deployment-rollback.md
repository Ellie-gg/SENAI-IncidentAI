# Deployment Regression Runbook

## Correlacionando Erros com Deploys

O primeiro passo diante de um aumento súbito de erros é checar o horário
do último deploy do serviço. Um salto no error rate logo após um deploy é
o sinal mais forte de regressão introduzida pela mudança.

### Quando Fazer Rollback

Faça rollback imediatamente se:
- O error rate está acima de 5% e subindo.
- O problema afeta um fluxo crítico (checkout, pagamento, autenticação).
- A causa não é óbvia em menos de 10 minutos de investigação.

Não é vergonha reverter primeiro e investigar depois em ambiente seguro —
o custo de manter produção quebrada enquanto se debuga ao vivo costuma ser
maior que o custo do rollback.

### Revisando o Diff

Depois do rollback, revise o diff do deploy revertido procurando por:
- Mudanças em paths pouco testados (feature flags, casos de borda).
- Alterações em configuração/env vars junto com o código.
- Migrações de banco que rodaram antes do rollback (não são revertidas
  automaticamente).

## Prevenção

Deploys canário ou rollout gradual reduzem o raio de impacto de uma
regressão antes que ela afete 100% do tráfego.
