# Cc e Bcc em novas mensagens

`prepare_send` e `send-prepare` aceitam listas opcionais `cc` e `bcc`:

```json
{"recipients":["para@example.test"],"cc":["copia@example.test"],"bcc":["oculto@example.test"],"subject":"Assunto","body":"Mensagem"}
```

O Webmail oferece os dois campos na composição de nova mensagem e mostra os
grupos na confirmação. O destinatário principal continua obrigatório. O limite
é de 1000 endereços únicos somando os grupos; a normalização remove duplicados,
com precedência Para, Cc, Bcc. Campos inválidos são recusados antes do journal.
Endereços Bcc são visíveis ao operador autorizado na própria prévia, nunca
devem ser copiados para descrição pública, logs ou corpo da mensagem.

Os grupos ficam congelados no rascunho com o token de confirmação existente.
Executar continua exigindo confirmação e claim único; falha incerta não repete
o envio. Sem `cc`/`bcc`, conserva-se o contrato anterior, inclusive a proteção
de listas no SMTP. Quando os campos são fornecidos, `recipients` representa
Para explícito; não usar essa forma para uma lista que deva permanecer oculta.

Gmail API recebe To/Cc/Bcc no MIME submetido ao provedor; Microsoft Graph usa
toRecipients/ccRecipients/bccRecipients. No SMTP normal, `send_message` da
biblioteca padrão extrai o envelope e remove Bcc dos bytes transmitidos.
Gmail SMTP/XOAUTH2 usa envelope explícito completo sem criar cabeçalho Bcc.
`recipientCount` inclui os três grupos, sem duplicação.

Respostas e encaminhamentos mantêm seu contrato anterior; uma solicitação de
Cc/Bcc adicional nesses fluxos é recusada explicitamente, nunca descartada.
`CmailApi.describe().sendFormats.cc/bcc` anuncia o suporte a novas mensagens.
Um consumidor que filtra propriedades deve transportar os campos até a
prévia oficial e manter sua confirmação exata. Atualizar fonte não instala
o wheel nem atualiza o adaptador de outro host.

Validação sintética: `python -s -m pytest -q tests/test_cc_bcc.py
tests/test_html_send.py tests/test_outgoing_attachments.py tests/test_message_actions.py`.
Não foi efetuado envio real ou homologação em contas nesta alteração.

Evidências de desenvolvimento nesta revisão: 394 testes não browser aprovados
(um probe real não executado), 21 testes de cópias e confirmação Webmail no
Edge headless aprovados. No consumidor CAW: 113 testes de contas, tools e SDK
nativos aprovados; após adicionar a regressão de envio direto com cópias, sete
testes focais de Cc/Bcc aprovados. São conferências do próprio desenvolvimento,
não homologação independente nem aceite do transporte real no DEV-FSND.
