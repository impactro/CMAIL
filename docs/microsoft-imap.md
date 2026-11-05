# Microsoft IMAP/SMTP com OAuth

Alternativa distinta do modo `microsoft` (Graph), disponível na 26.11.5e.
`mode: microsoft-imap` usa cliente público MSAL, código do dispositivo e
XOAUTH2. Não usa senha, segredo de aplicativo, Graph ou fallback automático.
Reutiliza leitura/gestão IMAP e envio MIME do CMAIL: templates, HTML, CID,
anexos, Para/Cc/Bcc, prévia congelada, confirmação, journal e recusa de replay.

## Configuração e identidade

Partir do JSON padrão schema 1.3. Definir `mode` como `microsoft-imap`;
`microsoft.clientId`, `tenantId` (UUID do tenant específico) e `account`.
`imap.account` e `imap.username` devem ser a mesma caixa. `passwordFile`,
`microsoft.clientSecretFile` e `redirectUri` ficam vazios. Endpoints fixos:
outlook.office365.com:993/SSL e smtp.office365.com:587/STARTTLS.
`server.openBrowser=false`: login é explícito, sem Webmail ou mudança de UI.

Em contas nomeadas, estado em `security/cmail/accounts/<connectorId>`;
cache em `oauth/microsoft-imap.dpapi`, protegido para o usuário Windows do
processo. O processo que autoriza deve ter a mesma identidade Windows do
consumidor. Não copiar DPAPI entre contas nem ampliar ACL como contorno.
Selecionar outro conector como `webmailConnectorId`. Hosts só vinculam os
principals que já autorizaram; conta configurada não concede acesso universal.

## Migração e autorização

Python canônico, sempre com `-s`; o módulo oferece CLI:

```powershell
python -s -m cmail.microsoft_imap --config config/cmail.outlook-smtp.json --agent-root . import-omail --source <cache-OMAIL-autorizado>
python -s -m cmail.microsoft_imap --config config/cmail.outlook-smtp.json --agent-root . status
python -s -m cmail.microsoft_imap --config config/cmail.outlook-smtp.json --agent-root . auth-start
python -s -m cmail.microsoft_imap --config config/cmail.outlook-smtp.json --agent-root . auth-finish
```

`import-omail` valida formato, conta única, tenant, aplicativo e escopos,
criptografa o cache no destino e não altera a origem. Não sobrescreve destino
existente e não comprova autenticação. Token revogado exige novo login; erro
50173 não se resolve copiando o arquivo novamente. `auth-start` retorna só
código público/URL Microsoft; device_code fica em DPAPI. `auth-finish` verifica
tenant/usuário antes de aceitar, sem login automático em outra conta.

Escopos: https://outlook.office.com/IMAP.AccessAsUser.All e
https://outlook.office.com/SMTP.Send. O tenant deve permitir esses protocolos
e SMTP AUTH para a caixa. Não mudar política Microsoft automaticamente.
Referência: [OAuth IMAP/SMTP Microsoft](https://learn.microsoft.com/en-us/exchange/client-developer/legacy-protocols/how-to-authenticate-an-imap-pop-smtp-application-by-using-oauth).

`status` faz login IMAP e AUTH/NOOP SMTP, sem MAIL/RCPT/DATA. Leitura posterior
deve ser delimitada. Envio real continua exigindo prévia e autorização específica;
SMTP aceito não comprova entrega. Não há cópia automática em Enviados por IMAP
APPEND nesta etapa: o comportamento efetivo depende da política do Exchange.
