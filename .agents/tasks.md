# Tarefas pendentes

Fila única do projeto. Seguir a [governança CES](../../../CServer/CES/padroes/project-governance.md).
Concluídos saem desta fila e vão para [histórico](../docs/history.md).

Pendências preexistentes preservadas; a padronização documental não revalida
seus estados nem autoriza efeitos operacionais. Conferir baseline antes da retomada.

## BUG

### BUG-CMAIL-NATIVE-READER-VIEWPORT-20261102 — Barra de ações excede o leitor estreito

- Fonte `feeabb8`, pacote `26.11.2.post4` com hash novo instalado no UniServer.
- Bateria completa: 327 aprovados e 1 falha.
  `test_context_toolbar_selection_mutations_and_responsive_layout`:
  `#toggleRead` em x=532, largura=40, dentro de iframe com 488 px.

## SUGESTÃO

### CMAIL-CONTAS-NOMEADAS — convergência dos conectores

Proposta solicitada por Fábio em 04/11/2026, registrada em
[contas nomeadas](../docs/named-connectors-proposal.md). Benefício: várias
contas do mesmo provedor, transporte único, templates/inline/anexos no CMAIL,
sem duplicar disparadores nos consumidores. Webmail mantém conector fixo.
O desenvolvimento depende da revisão da proposta; análise concluída não
autoriza implementação, nova UI, migração de credenciais ou envio real.

## BACKLOG

### CMAIL-RENDER-CONTEXTUAL — aceite restante

VALIDATION: responsividade/PWA/dois usuários e autenticação em processo independente.
Lista/busca/leitor CAW/Webmail desktop já conferidos. Gmail5884 aguarda cadastro/consentimento em
CServer:CMAIL-GOOGLE-5884; não repetir desenvolvimento ou instalação.

### GMAIL-FILE — aceite do consumidor Vitrine

BLOCKED: Gmail API retornou SERVICE_DISABLED no consumidor; validar habilitação no projeto correto e
configuração pelo dono Vitrine. Refresh funcionou, mas envio real não foi aceito.
SMTP XOAUTH2 já existe no CMAIL (`gmailFile.transport="smtp"`, schema 1.3);
o aceite dessa rota no consumidor é separado, sem fallback ou troca automática.
