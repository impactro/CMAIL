---
name: enviar-email
description: Preparar e executar envio unitário ou em lista pelo CMAIL com confirmação explícita.
---

# Enviar E-mail

Nunca pule a prévia. Primeiro use `send-prepare --input-json <arquivo>` e mostre
destinatários, quantidade, assunto e resumo do corpo. Somente após autorização
específica use `send-execute --draft-id <id> --confirmation-token <token>
--execute` dentro dos dez minutos de validade.

O token autoriza apenas aquele rascunho e é consumido uma vez. Falha depois do
início do SMTP fica `uncertain`; não repita automaticamente, pois o servidor
pode ter aceitado a mensagem antes de interromper a resposta.
