# Leitor nativo incorporado

Desde26.11.2d/Python26.11.2.post3, o host pode montar o webmail com
`?readerOnly=1&folder=<pasta>&messageId=<id>&hostRequest=<nonce>`.
O modo somente funciona na montagem incorporada e não concede autoridade.
Pasta e mensagem são resolvidas pelas APIs autenticadas normais; pasta ausente
ou incompatível falha antes da leitura do item. O body continua sendo texto.

O cabeçalho nativo mantém ações permitidas pelo provedor e pelo Principal:
responder, responder a todos, encaminhar, mover, arquivar, marcar leitura e
excluir. Controles indisponíveis não são expostos. Prévia/execução de envio,
CSRF e confirmação de exclusão definitiva preservam seus contratos anteriores.
O host não implementa uma segunda cópia dessas operações.

O host cuida da lista/pastas; o leitor consulta apenas o item selecionado e
metadados necessários, sem listar novamente as mensagens. Efeitos aceitos
notificam o parent pela origem, frame e nonce esperados. O aviso só atualiza a
apresentação; não autoriza nem repete ações. A identidade do host descarta o
frame anterior. Novo e-mail conserva seu compositor separado em memória.

Validação:314testes Python e2testes DOM com provedor fictício. Para os testes
DOM, disponibilizar jsdom no ambiente de desenvolvimento e executar
`node --test tests/reader_embed.test.cjs` com CMAIL_TEST_PYTHON apontando ao Python
canônico, se necessário. Nenhum envio/exclusão real foi feito neste aceite.
