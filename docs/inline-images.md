# Imagens internas por CID

Incluídas na distribuição `26.10.28`. A instalação efetiva e o suporte anunciado
pela API devem ser verificados em cada consumidor.

Extensão opcional de `prepare-send`/`execute-send`. Usa o mesmo Principal,
capacidade `mail.send`, prévia exata, token unitário e journal por proprietário.
Não adiciona conta, SSO, permissões, arquivos externos ou repetição de envios.
Não altera o schema do banco nem o limite de 200 mil caracteres do HTML.

`CmailApi.describe().sendFormats.inlineImages` anuncia suporte real na API.
Consumidores devem verificar esse campo, não inferir pela versão ou ignorar
a ausência. `attachments` continua `false`: não há envio de arquivos gerais.

```json
{
  "recipients": ["pessoa@example.test"],
  "subject": "Apresentação",
  "body": "Alternativa textual completa.",
  "bodyHtml": "<p>Apresentação.</p><img src=\"cid:marca\" alt=\"Marca\">",
  "inlineImages": [
    {
      "contentId": "marca",
      "contentType": "image/png",
      "contentBase64": "BASE64_DOS_BYTES_APROVADOS",
      "name": "marca.png"
    }
  ]
}
```

`contentId`, `contentType` e `contentBase64` são obrigatórios; `name` é opcional.
O exemplo é estrutural: substituir o marcador por base64 de imagem real.
Aceita PNG/JPEG, até oito imagens e dois MiB de bytes decodificados no conjunto.
Confere base64, assinatura do formato, IDs e nomes limitados. Não é um decoder,
antivírus ou avaliação visual. SVG, caminhos, URLs de download, dados com tipo
divergente e campos desconhecidos são recusados antes de criar o rascunho.

Cada ID fornecido deve aparecer em `img src="cid:ID"` e cada referência deve
possuir bytes correspondentes. A mesma imagem pode aparecer várias vezes no
HTML com o mesmo CID, sem duplicar a parte MIME. IDs duplicados na lista e
imagens não usadas são recusados. A integração não busca URLs nem lê caminhos.

O snapshot confirmado contém corpo e bytes. A prévia também fornece
`inlineImageSummary` com ID, nome, tipo, quantidade de bytes e SHA-256.
Não copiar base64 para auditoria ou telemetria; a auditoria mantém somente
seus metadados mínimos anteriores. Alterar o arquivo original após preparar
não modifica o snapshot. O token não aceita corpo ou imagens substitutos.

Gmail API, Gmail por arquivo/SMTP e IMAP/SMTP usam a mesma construção
`multipart/alternative` com HTML `multipart/related`, `Content-ID` e disposição
`inline`. Graph recebe `fileAttachment` com `isInline=true`, somente para os
raster referenciados. O modo demo valida e permanece sem efeitos externos.
Clientes de e-mail ainda controlam como exibem imagens; CID não promete leitura.

CLI Gmail por arquivo, somente preparação:

```text
python -s -m cmail.enviar --gmail --config-file CONFIG --to DESTINO --subject ASSUNTO --body-file mensagem.txt --html-file email.html --inline-images-json imagens.json
```

O arquivo JSON contém somente a lista `inlineImages`, incluindo bytes base64,
nunca caminhos. É lido com limite de tamanho. A execução continua aceitando
somente `--execute --draft-id ID --confirmation-token TOKEN`, sem novos campos
ou arquivo de imagens. Falha incerta após claim permanece sem replay automático.

Testes: `python -s -m pytest tests/test_inline_images.py -q`. A validação usa
somente imagens sintéticas, journal temporário e providers falsos, sem rede.
Receber MIME local não equivale a enviar, receber ou renderizar no Gmail real.

Referências: [MIME related no Python](https://docs.python.org/3.12/library/email.examples.html)
e [imagens inline no Microsoft Graph](https://learn.microsoft.com/en-us/graph/api/resources/fileattachment?view=graph-rest-1.0).
