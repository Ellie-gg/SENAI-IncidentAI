# Auth Failure Runbook

## 401/403 em Massa

Quando usuários com credenciais válidas começam a receber 401/403 em
massa (não usuários isolados), a causa raiz raramente é do lado do
usuário — é quase sempre uma mudança do lado do serviço.

### Causas Comuns

- **Rotação de chave de assinatura sem invalidar cache**: se a chave usada
  para assinar/validar tokens foi rotacionada mas algum serviço ainda tem
  a chave antiga em cache, ele passa a rejeitar tokens válidos assinados
  com a chave nova.
- **Expiração de certificado**: certificados TLS ou de assinatura de token
  expirados derrubam autenticação inteira de uma vez, de forma abrupta.
- **Relógio dessincronizado**: tokens com `exp`/`iat` são sensíveis a
  clock skew entre serviços.

## Mitigação

Forçar um refresh do cache de chaves/certificados costuma resolver
rotação de chave imediatamente. Reduzir o TTL do cache de chaves evita que
o próximo evento de rotação cause o mesmo problema.

## Prevenção

Automatizar a rotação de chaves com um período de sobreposição (chave
antiga e nova válidas simultaneamente por um tempo) evita esse tipo de
corte abrupto.
