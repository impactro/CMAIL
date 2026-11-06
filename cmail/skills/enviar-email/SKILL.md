---
name: enviar-email
description: Preparar e executar envio unitário ou em lista pelo CMAIL com confirmação explícita.
---

# Enviar E-mail

Esta skill serve a CA/CAX e exige `Principal` validado com `mail.send`. Não use
cookie, token de sessão web nem access token Microsoft como assertion. Nunca
pule a prévia. Pela API Python, chame `prepare_send`; pela CLI local, use
`send-prepare --input-json <arquivo>`. Mostre
destinatários, quantidade, assunto e resumo do corpo. Somente após autorização
específica chame `execute_send` ou use `send-execute --draft-id <id>
--confirmation-token <token> --execute` dentro dos dez minutos de validade.

O token autoriza apenas aquele rascunho e é consumido uma vez. Falha depois do
início do SMTP fica `uncertain`; não repita automaticamente, pois o servidor
pode ter aceitado a mensagem antes de interromper a resposta.

Para aplicar template e assinatura configurados, envie `appearance: {}` a
`prepare_send`; o CMAIL resolve a herança empresa/pessoa no workspace validado.
Mostre a prévia final em texto e HTML, sem duplicar assinatura. Não misture
`appearance` com `bodyHtml` pronto. `execute_send` consome o mesmo snapshot;
não prepare novamente depois da confirmação nem troque destinatário ou conteúdo.
Falha com `requires_reconnect` exige reconectar pelo perfil do CAW. Não tente
outra conta, copiar token, renovar o login automaticamente ou repetir o envio.

Responder, responder a todos e encaminhar também são efeitos externos: mostre
destino e conteúdo e obtenha confirmação específica antes de chamar a operação.

## Conta, apresentação e anexos

Use o alias de conta configurado no host; Gmail, Graph e IMAP/SMTP mantêm
suas próprias autenticações no componente. Escolher um template não escolhe
a conta. Marcas, destinatários por cliente e vínculo conta/template pertencem
ao cadastro do agente consumidor, não a esta skill genérica.

Templates podem separar título, subtítulo, conteúdo e frase final. O adaptador
do consumidor resolve esses campos antes de `prepare_send`; a API recebe
`subject`, `body` e opcionalmente `bodyHtml`. Sem assunto explícito, o consumidor
pode compor título e subtítulo. Não enviar placeholders ou HTML ativo.

Anexos comuns: `attachments` na API contém nome, tipo e bytes congelados pelo
backend; na ferramenta CAW use referências de arquivo permitidas, nunca base64
gerado pelo modelo. Para/Cc/Bcc devem permanecer iguais na prévia e execução.
Imagem inline/CID e anexo comum são recursos distintos; não omita um anexo
nem substitua por link para contornar falta de suporte. Prévia não é envio;
aceitação do provedor não comprova entrega, leitura ou cópia em Enviados.
