# API Python do CMAIL

Configuração administrativa é uma API Python separada das capabilities da caixa:
`CmailConfiguration` / `ConfigurationConflict`, disponíveis em `cmail`.
Leitura, validação, revisão, catálogo CES e aplicação estão documentados em
[configuração pelo host](docs/configuration-host.md). Não há novo endpoint HTTP
administrativo. O host valida a permissão do administrador antes de expor essa API.

`appearance`, `save_appearance` e `render_appearance` configuram template e
assinatura independentes por proprietário, com `mail.send`. A aplicação no
`prepare_send` é explícita por `appearance: {}`. `prepare_message_action`
prepara respostas/encaminhamentos no mesmo journal confirmado, com `mail.send`
e `mail.read`. Contratos e serviços opcionais do host em
[aparência do e-mail](docs/mail-appearance.md).

Novo trilho local a partir da distribuição `26.10.19`: schema de configuração
`1.2`, modo `gmail-file`, `Config.from_file` + `create_api` +
`Principal.local_operator`. Não aceita owner/identidade web; os modos OAuth
existentes mantêm seu contrato. Veja [autenticação por arquivo](docs/gmail-file.md).
`render_email_template(path, *, body, fields=None, html_fields=None)` devolve
`body`/`bodyHtml` sem preparar/enviar; contrato em [templates](docs/email-templates.md).

Extensão aditiva incluída na distribuição `26.10.28`: `inlineImages` no payload de preparação conserva
bytes PNG/JPEG junto do HTML confirmado. Verificar primeiro
`CmailApi.describe().sendFormats.inlineImages`; contrato e limites em
[imagens internas CID](docs/inline-images.md). Não há acesso a arquivos ou
downloads no provider, nem alteração da autorização de envio.

`cmail.create_api(config)` entrega a fachada estável para runtimes agentes. A
mesma factory é descoberta pelo entry point
`crania_agent.component_apis:cmail`; o descritor CM 2 continua isolado em
`crania_agent.components:cmail`.
Ela não recebe cookie, bearer token web nem módulo interno do host. Toda chamada
recebe um `Principal` já validado pelo runtime consumidor e verifica a
capacidade necessária antes de tocar a conta.

O descritor CM 2 permanece estritamente compatível com o Component Manager e
lista apenas operações CLI com IDs simples. Operações estruturadas da API não
são misturadas nesse descritor: `CmailApi.describe()` publica separadamente o
schema `1.0`, factory, tipo de principal, capabilities e efeitos.

```python
from cmail import Config, Principal, create_api

config = Config.load()
api = create_api(config)

# O CAX é responsável por validar sua assertion antes de construir o objeto.
principal = Principal(
    identity_id="identidade-previamente-vinculada-no-cmail",
    email="usuario@example.com",
    capabilities=frozenset({"mail.read", "mail.manage", "mail.send"}),
)

folders = api.folders(principal)
messages = api.messages(principal, folders[0]["id"], limit=25)
```

## Capacidades

- `mail.read`: status ao vivo, pastas, mensagens, anexos, contatos, diretório,
  calendários e disponibilidade quando suportados pelo provider;
- `mail.manage`: marcar leitura, mover mensagens, mover para a lixeira, excluir
  definitivamente e gerir eventos com confirmação
  explícita;
- `mail.send`: preparar, confirmar, responder e encaminhar;
- `lists.manage`: consultar e manter listas locais da identidade.

Um CAX mínimo pode importar o módulo, descobrir as skills empacotadas pelo
descritor CM 2 e operar a conta autenticada sem instalar o CA completo. O host
é dono da validação de sua assertion; CMAIL é dono do vínculo local da
identidade, do provedor e das capacidades exigidas por operação.

`api.message_actions(principal)` e `GET /api/message-actions` publicam os
controles disponíveis (`setRead`, `move`, `trash`, `deletePermanently`, `reply`, `forward`, `send`, `lists`),
combinando suporte do provider e capacidades concedidas. IMAP consulta suporte
do servidor a `MOVE`/`UIDPLUS`/`IMAP4rev2` por CAPABILITY depois do login,
sem depender do cache da conexão anterior à autenticação.
`set_read`, `move`, `reply` e `forward` aceitam `folder="INBOX"` como argumento
nomeado adicional; em IMAP, o UID pertence necessariamente a essa pasta.
As rotas web correspondentes aceitam `folder` no JSON. Clientes antigos
continuam usando INBOX por padrão. Movimentar usa o ID real da pasta de destino;
a interface oferece arquivo/lixeira somente quando identifica essas pastas.
Nenhuma ação faz expurgo geral da caixa. Resposta/encaminhamento IMAP conservam a confirmação explícita;
o encaminhamento inclui somente texto, sem anexos.
Os itens de pasta podem declarar `canMoveTo=false`; a interface exclui esses
destinos do seletor. Gmail usa isso para Enviados/Rascunhos, cujos marcadores
de sistema não podem ser aplicados manualmente, conforme o
[contrato de marcadores Gmail](https://developers.google.com/workspace/gmail/api/guides/labels).

### Excluir: operações distintas

| Intenção | API Python | HTTP | Efeito |
| --- | --- | --- | --- |
| Mover para a lixeira | `trash_message(principal, id, folder="INBOX")` | `POST /api/messages/{id}/trash` | Imediato e recuperável; não exige confirmação |
| Excluir definitivamente | `delete_permanently(principal, id, folder=TRASH_ID, confirmed=True)` | `POST /api/messages/{id}/delete-permanently` | Exclusão definitiva de uma mensagem já na lixeira |

Ambas recebem `folder` no JSON; somente a exclusão definitiva exige
`confirmed: true`. O parâmetro Python legado `confirmed` de `trash_message`
continua aceito, mas não é necessário. Ambas exigem `mail.manage`; as rotas
web também exigem CSRF. O serviço resolve a lixeira
da conta, recusa a exclusão definitiva fora dela e registra ações separadas
`trash`/`delete-permanently`. Não existe parâmetro genérico que converta uma
movimentação em exclusão definitiva, nem exclusão definitiva automática quando
a conta não oferece lixeira.

O botão visual é sempre **Excluir**, com o mesmo ícone e cor. Fora da lixeira,
ele move a mensagem imediatamente, sem modal; dentro dela, a confirmação diz **Excluir
definitivamente** e informa que a mensagem não poderá ser recuperada pelo webmail.
Existindo lixeira, `trash` é independente do flag genérico `move`. Falta de
capacidade de exclusão definitiva mantém o botão contextual desabilitado na
lixeira, com motivo no título.

IMAP aplica STORE/UID EXPUNGE somente ao UID selecionado, exigindo UIDPLUS ou
IMAP4rev2. Graph verifica o `parentFolderId` real e usa a ação
[permanentDelete](https://learn.microsoft.com/en-us/graph/api/message-permanentdelete?view=graph-rest-1.0),
sujeita à retenção da Microsoft. Gmail verifica o marcador TRASH real e exige
o grant `https://mail.google.com/` para
[messages.delete](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/delete);
o OAuth web atual com `gmail.modify` mantém lixeira disponível e exclusão
definitiva indisponível. Não há ampliação automática de consentimento.

No executável standalone, uma raiz de configuração/estado representa uma única
conta e o `owner_id` permanece vazio. Duas contas exigem duas raízes e duas
portas. O preenchimento de `owner_id` é reservado à composição por um host que
derive esse valor de uma identidade confiável, como o `workspaceId` autenticado
do CA; ele nunca é um seletor livre de conta na interface standalone.

O host consulta e administra a conexão sem receber tokens:

```python
state = api.connection_status(workspace_id)
api.set_webmail_enabled(workspace_id, False)  # só oculta/bloqueia a UI
api.disconnect_owner(workspace_id)            # revoga a autorização da caixa
```

`webmailEnabled` não é uma capability de e-mail. A preferência controla apenas
a interface humana; `Principal` e as capabilities continuam governando o uso
das operações Python pelo agente.

Envio comum continua em duas etapas:

```python
preview = api.prepare_send(principal, {
    "recipients": ["destinatario@example.com"],
    "subject": "Assunto",
    "body": "Conteúdo",
    "bodyHtml": "<p>Conteúdo com <strong>formatação</strong>.</p>",
})

# Execute somente depois da confirmação específica do usuário.
result = api.execute_send(
    principal, preview["draftId"], preview["confirmationToken"]
)
```

Falha após o claim do rascunho fica `uncertain` e não é repetida
automaticamente. O caller não deve criar um `Principal` a partir de parâmetros
livres enviados pelo usuário, nem repassar cookies ou tokens OAuth ao agente.

`bodyHtml` é opcional, com limite de 200.000 caracteres. `body` continua obrigatório
como alternativa em texto. HTML e texto pertencem ao mesmo rascunho confirmado;
Gmail/SMTP produzem MIME multipart/alternative e Graph envia body HTML.
O consumidor renderiza o template antes de preparar e mostra a prévia completa.
Anexos de envio não estão implementados; a preparação rejeita `attachments` não
vazio para evitar confirmar uma mensagem que perderia seus documentos.
