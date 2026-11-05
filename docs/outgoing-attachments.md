# Anexos comuns — preparo e execução

Disponível na API Python de envio novo, tanto CmailApi quanto BoundMailbox.
Não muda leitura de anexos recebidos, OAuth, capacidades ou UI. O host resolve
artefatos autorizados e fornece conteúdo; o CMAIL não abre paths nem baixa URLs.
Não entregar credenciais ou grandes blobs ao modelo: resolução é função do host.

## Entrada e limites

`prepare_send(principal, payload)` aceita `attachments` como lista de objetos
com exatamente `name`, `contentType` e `contentBase64`. O facade já vinculado
usa `mailbox.prepare_send(payload)`. Exemplo de descritor:

```json
{"name":"proposta.pdf","contentType":"application/pdf","contentBase64":"JVBERi0xLjQ="}
```

Até8 arquivos, nomes até120 caracteres sem controle/separadores de caminhos,
MIME simples minúsculo e base64 estrito. Arquivos vazios são rejeitados.
O MIME é declarativo, não uma validação do formato ou varredura antivírus.
O conteúdo não é aberto nem executado pelo envio.

Limite inicial conservador: **2 MiB decodificados somados entre todos os
arquivos e imagens inline**. Snapshot JSON com anexos até3 MiB serializados,
incluindo corpo/metadados. Uploads grandes não estão disponíveis.

| Provedor | Representação e limite |
| --- | --- |
| Gmail API | MIME multipart/mixed, corpo/HTML/related CID e attachment, mesmos limites de preparo. |
| Gmail SMTP/XOAUTH2 | Mesmo montador MIME; sem nova conexão ou refresh durante preparo. |
| IMAP/SMTP | Mesmo MIME no SMTP existente. IMAP é apenas leitura. |
| Microsoft Graph | fileAttachment/isInline=false; CID mantém isInline=true. Requisição pequena abaixo de4 MiB, sem upload session. |
| Demo | Valida estrutura, sem envio externo. |
| Provedor externo | Deve declarar supports_attachments=True; caso contrário, preparo rejeita. |

As assinaturas `Provider.send(..., attachments=None)` e
`inline_images.add_body(..., attachments=None)` são aditivas. Chamadas sem
arquivos continuam com as opções anteriores; não se envia keyword novo para
provedores legados quando a prévia não contém anexos.

## Snapshot confirmado

Durante preparo, os bytes normalizados ficam no snapshot privado `mail_drafts`
do Store da conta. Não existe dependência posterior do arquivo de origem.
Se o host modificar/apagar o original, o snapshot continua sendo o conteúdo
confirmado. Trocar conteúdo exige outra preparação/confirmação.

A prévia expõe `attachmentSummary` e `attachmentManifest`: nome, MIME, bytes e
SHA256, sem base64 dos arquivos comuns. Imagens inline conservam seu contrato
próprio de prévia. O hash não é recibo de entrega nem assinatura contra um
administrador capaz de alterar simultaneamente dados e manifesto do banco.

`Store.claim` confere o manifesto antes de marcar sending. Conteúdo divergente
ou arquivo removido do snapshot aborta, sem chamar provedor. O serviço fixa
também conta, owner, identidade, remetente esperado e transporte. Mudança desse
vínculo exige nova prévia; rotação normal de token não altera o vínculo.
O registro nomeado usa o Store isolado do conector, impedindo claim de prévia
de outra caixa ou proprietário. A execução não aceita substituição de arquivos.

Validade continua10 minutos. Expiração e claim único são os do CMAIL.
Prévias com arquivos usam status interno `prepared-files-v1`; executores antigos,
que aceitam apenas `prepared`, não podem enviar essa prévia sem os anexos em
um rollback. Prévias antigas sem arquivo continuam aceitas. Não converter o
status manualmente; preparar outra prévia com a versão apropriada.

Após iniciar execução, falha mantém resultado incerto e não há repetição automática
nem fallback para outra conta/provedor. Dados do snapshot seguem a retenção
existente de drafts no Store; não foi adicionada purga de dados privados nesta
etapa. Cada snapshot é limitado; retenção global do histórico é assunto próprio.

## Fora desta etapa

Anexos comuns em resposta/encaminhamento são recusados na preparação, sem
descarte silencioso. Não há promessa de preservar anexos originais em forward.
To/Cc/Bcc completo, CLI de anexos, seletor/upload visual, integração de artefatos
dos consumidores e homologação com contas reais ficam para etapas próprias.
Envio real continua exigindo prévia, confirmação e autorização do pedido.

Testes usam SMTP/HTTP simulados, bytes sintéticos e nenhuma conta real.
