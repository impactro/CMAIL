# API Python do CMAIL

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
- `mail.manage`: marcar leitura, mover mensagens e gerir eventos com confirmação
  explícita;
- `mail.send`: preparar, confirmar, responder e encaminhar;
- `lists.manage`: consultar e manter listas locais da identidade.

Um CAX mínimo pode importar o módulo, descobrir as skills empacotadas pelo
descritor CM 2 e operar a conta autenticada sem instalar o CA completo. O host
é dono da validação de sua assertion; CMAIL é dono do vínculo local da
identidade, do provedor e das capacidades exigidas por operação.

No executável standalone, uma raiz de configuração/estado representa uma única
conta e o `owner_id` permanece vazio. Duas contas exigem duas raízes e duas
portas. O preenchimento de `owner_id` é reservado à composição por um host que
derive esse valor de uma identidade confiável, como o `workspaceId` autenticado
do CA; ele nunca é um seletor livre de conta na interface standalone.

Envio comum continua em duas etapas:

```python
preview = api.prepare_send(principal, {
    "recipients": ["destinatario@example.com"],
    "subject": "Assunto",
    "body": "Conteúdo",
})

# Execute somente depois da confirmação específica do usuário.
result = api.execute_send(
    principal, preview["draftId"], preview["confirmationToken"]
)
```

Falha após o claim do rascunho fica `uncertain` e não é repetida
automaticamente. O caller não deve criar um `Principal` a partir de parâmetros
livres enviados pelo usuário, nem repassar cookies ou tokens OAuth ao agente.
