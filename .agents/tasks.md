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

## BACKLOG

### CMAIL-VALIDACAO-DEVSERVER-20261105 — imagem inline e downloads

VALIDATION: resta conferir a apresentação visual de imagem inline recebida e
downloads PDF/XML no leitor. Lista Gmail25 e-mails, pasta INBOX, leitor da
mensagem sintética Dorotech e nomes dos três anexos já conferidos no Edge.
As seis rotas do run CMAIL-20261105-FD-01 tiveram recebimento confirmado.
Não repetir os envios. Detalhes em docs/validation/devserver-20261105.md.

### CMAIL-CC-BCC-DEV-FSND — atualizar e validar o consumidor

Cc/Bcc em novas mensagens implementados no CMAIL26.11.5d e CA26.11.5e.
Validar instalação e preservação dos grupos na prévia oficial no DEV-FSND
pelo chat FSND CA Fábio, conforme pedido. A validação anterior Gmail/IMAP
permanece no histórico; não repetir sua migração nem habilitar Outlook.
Envio real exige prévia e confirmação específica; testes de desenvolvimento
foram sintéticos. Não duplicar transportes SMTP no adaptador pessoal.

### CMAIL-CONTAS-NOMEADAS — etapas restantes

Primeira etapa autorizada em04/11 e entregue na fonte: registro Python,
estado isolado e adaptador legado, conforme [contrato](../docs/named-connectors.md).
Permanecem: editor do registro, onboarding/callback por conector, aliases,
conta de serviço gmail-file e consumidores CA/CAX/CWH/CCI/CVAI. Anexos comuns
em envio novo estão entregues; respostas/encaminhamentos e uploads grandes
permanecem fora desse contrato.
CCI já aceita o mapa de readers na fonte 26.11.5a; adaptação/implantação pelo
host e homologação com múltiplas caixas reais continuam pendentes.
Webmail/instalações não migrados. Reabrir pelo contrato e testes, sem copiar
tokens, alterar autenticação ou executar envio por efeito desta fila.

### CMAIL-VALIDACAO-DISTRIBUIDA — Homologar provedores na máquina dona das contas

Testes categorizados, plano privado exemplo e bundle de leitura foram entregues
em 26.11.5a. DEV executou apenas cenários sintéticos. Conferir por perfil
IMAP, Gmail OAuth web, Gmail API/arquivo, Gmail SMTP/XOAUTH2 e Outlook/Graph,
seguindo docs/validation/README.md. Contas ausentes ficam não executadas;
status SMTP não comprova envio. Instalação/execução real exigem autorização
do ambiente. Entregar recibo sanitizado e documentação validada fora do checkout.

### CMAIL-RENDER-CONTEXTUAL — aceite restante

VALIDATION: responsividade/PWA/dois usuários e autenticação em processo independente.
Lista/busca/leitor CAW/Webmail desktop já conferidos. Gmail5884 aguarda cadastro/consentimento em
CServer:CMAIL-GOOGLE-5884; não repetir desenvolvimento ou instalação.

### GMAIL-FILE — aceite do consumidor Vitrine

BLOCKED: Gmail API retornou SERVICE_DISABLED no consumidor; validar habilitação no projeto correto e
configuração pelo dono Vitrine. Refresh funcionou, mas envio real não foi aceito.
SMTP XOAUTH2 já existe no CMAIL (`gmailFile.transport="smtp"`, schema 1.3);
o aceite dessa rota no consumidor é separado, sem fallback ou troca automática.
