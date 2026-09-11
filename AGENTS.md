<!-- CRANIA_GLOBAL_REF_BEGIN -->
> Regra global: este projeto também obedece ao padrão CrânIA/Fábio Souza em `../../AGENTS.md`.
> Este repositório deve consultar `../../CServer/CES/padroes/README.md` para padrões de PM, SM, DEV, QA, OPS, REV e SEC.
<!-- CRANIA_GLOBAL_REF_END -->
# AGENTS - CMAIL

Antes de desenvolver, revisar ou migrar, leia o README local, `../AGENTS.md` e
os padrões canônicos do CServer.

CMAIL é um Component Module genérico. Não importar identidade, usuários,
regras departamentais ou credenciais de um agente. Segredos são referências
externas; `.env`, estado, logs e conteúdo de e-mail não entram no Git.

Leituras podem ser executadas quando configuradas. Envio unitário ou em lote é
efeito externo e exige prévia, confirmação específica e `--execute`. Falha após
início do SMTP é tratada como estado incerto; não repetir automaticamente.
