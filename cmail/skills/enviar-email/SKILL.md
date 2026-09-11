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

Responder, responder a todos e encaminhar também são efeitos externos: mostre
destino e conteúdo e obtenha confirmação específica antes de chamar a operação.
