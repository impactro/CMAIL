# connectors.config.example.json

Exemplo executável apenas no modo demo, com duas caixas fictícias, sem OAuth.
Não substituir a configuração de uma instalação existente por este exemplo.
`root` da composição deve ser a raiz da instância; caminhos partem do JSON.

Campos do registro: `schemaVersion` string2.0; `webmailConnectorId` ID existente;
`connectors` objeto com configurações nativas completas por ID. Cada
`state.directory` resolve para `root/security/cmail/accounts/<id>`.
IDs: letras minúsculas, números, `_` e `-`, letra inicial, até64 caracteres.

Cada filho segue o contrato nativo em [cmail.config.md](cmail.config.md):
`mode` escolhe provedor; `server` conserva opções de host/porta/browser/sessão;
`state` escolhe estado isolado; `microsoft` e `imap` contêm campos requeridos
pelo schema1.0, vazios quando não usados. Aqui `imap.account` diferencia as
caixas fictícias. Portas declaradas não iniciam servidores na composição.
Para Gmail, o filho deve usar schema1.1+ e a seçãoGoogle nativa completa.

Contrato e API: `share/doc/crania-cmail/docs/named-connectors.md` no pacote,
ou `docs/named-connectors.md` no checkout. Alterações exigem construir novo
registro; não há editor, hot-reload, migração ou callback novo nesta etapa.
