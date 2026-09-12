# CMAIL

`CMAIL` é o nome técnico do módulo independente que reúne webmail, leitura de
pastas e mensagens, listas de destinatários e disparo controlado de e-mail.
Versão do componente: `26.9.12c` (pacote Python `26.9.12.post2`).

O módulo agora é dono da ferramenta Webmail e pode existir de duas formas com
o mesmo código: aplicação FastAPI standalone ou subaplicação ASGI incorporada por outro
runtime. Ele não importa `ca.*`, não reutiliza banco, sessão ou token do
CraniaAgent e oferece uma API Python pública baseada em identidade e
capacidades.

## Execução

Cada autoexecução standalone representa exatamente uma conta. Para manter duas
contas, crie duas pastas operacionais com `.env`/`.bat`, JSON, estado e portas
diferentes; o pacote Python instalado continua único. O modo standalone não usa
`workspaceId` para multiplicar caixas dentro do mesmo processo.

O modo inicial `setup` abre um assistente local para escolher Outlook, Gmail ou
IMAP/SMTP. Depois de salvar, o processo standalone se reinicia. Outlook e Gmail
iniciam OAuth obrigatório sem pedir o e-mail antecipadamente: a primeira
identidade verificada pelo provedor fica vinculada à instância, e outra conta é
recusada até uma reconfiguração explícita. IMAP usa os dados informados na
configuração e abre o webmail local.
Segredos são gravados em arquivos com ACL restrita; o JSON mantém somente as
referências. Ao reconfigurar, os campos não sensíveis retornam preenchidos e um
segredo vazio preserva a referência já configurada. O antigo modo `demo`
permanece apenas para testes controlados.

O `.env` possui somente `CMAIL_CONFIG_FILE=<caminho>`. O JSON indicado segue
schema fechado `1.1`; chaves ausentes ou desconhecidas são recusadas e caminhos
relativos partem da pasta desse JSON. Configure nele `microsoft.clientId`,
`microsoft.tenantId`, `microsoft.clientSecretFile` e
`microsoft.redirectUri`. O redirect deve usar `localhost` e terminar em
`/auth/callback`. A aplicação registrada recebe apenas
`openid`, `profile`, `email`, `User.Read`, `Mail.ReadWrite` e `Mail.Send`.
O MSAL inclui `openid/profile` no protocolo; o CMAIL exclui explicitamente
`offline_access`, portanto a expiração do token pode exigir novo login.

O schema `1.0` anterior continua legível para rollback. O modo `imap` agora
também abre a interface web, sempre como instância local de uma única conta.
Gmail usa OAuth próprio e a API Gmail com `openid`, `email`, `gmail.modify` e
`gmail.send`; Outlook mantém Microsoft Graph com as permissões já documentadas.

```powershell
python -m cmail check-config
python -m cmail status
python -m cmail list-folders
python -m cmail list-messages --folder INBOX --limit 50
python -m cmail serve
```

Dependências web declaradas: FastAPI, Starlette/Jinja e Uvicorn. Para validar o checkout e
construir o wheel sem instalar no host:

```powershell
python -m pytest -q
python -m pip wheel . --no-deps --wheel-dir dist
```

`serve` usa Uvicorn e abre `http://127.0.0.1:7420/`. A versão aceita
IMAP/SMTP com SSL ou STARTTLS. Corpos HTML são convertidos em texto antes de
chegar à interface; imagens remotas não são carregadas. Anexos são apenas
inventariados nesta primeira ejeção.

No Outlook e no Gmail, a ferramenta lista pastas e mensagens, lê o corpo como texto,
marca lida/não lida, move, responde, encaminha e envia. Contatos, calendário,
download de anexos, proxy de imagens, campanhas e editor HTML rico não fazem
parte desta fatia porque exigem contratos e permissões adicionais.

No Microsoft Graph, a listagem usa somente propriedades do recurso
`mailFolder`; o ID da caixa de entrada é resolvido pela rota conhecida
`/me/mailFolders/inbox`. Isso evita depender de `wellKnownName` dentro do
`$select`, que o contrato dessa coleção não expõe.

## Listas e disparo

Uma lista é importada por JSON:

```json
{"name":"Clientes ativos","recipients":[{"name":"Exemplo","address":"pessoa@example.com"}]}
```

```powershell
python -m cmail lists --input-json lista.json
python -m cmail send-prepare --input-json mensagem.json
python -m cmail send-execute --draft-id ID --confirmation-token TOKEN --execute
```

O JSON de mensagem aceita `recipients` ou `listId`, além de `subject` e `body`.
A preparação não envia nada: cria journal e token único com validade de dez
minutos. A execução consome o token antes do SMTP. Se houver falha depois disso,
o estado fica incerto e não existe retry automático.

Quando há vários destinatários, o SMTP usa envelope Bcc e não publica a lista
no cabeçalho recebido por cada pessoa.

## Component Manager

O wheel publica `cmail = cmail.cm:describe` em
`crania_agent.components`, contrato CM 2. As skills vivem em `cmail/skills/` e
são descobertas pelo CraniaAgent sem cópia. Instalação e habilitação continuam
separadas; um agente seleciona somente as operações realmente permitidas.

O descritor CM 2 mantém somente operações CLI com IDs aceitos pelo Component
Manager. A factory pública `cmail:create_api` e seu contrato estruturado ficam
separados em `CmailApi.describe()` e no entry point
`crania_agent.component_apis`. Um host cria um `Principal` somente depois
de validar sua própria assertion e concede
capacidades explícitas (`mail.read`, `mail.manage`, `mail.send` e
`lists.manage`). Cookies e tokens web nunca são usados como autorização da API
Python. Veja [API.md](API.md).

A aplicação ASGI é publicada em `crania_agent.component_apps` como
`cmail.web:create_component_app`. A fábrica segue o contrato comum
`(agent_root, host_services)`; a autenticação da conta permanece própria. Somente
em composição o principal confiável do host permite uma caixa por `workspaceId`;
isso não altera a cardinalidade unitária da autoexecução local. Em composição,
`configFile` aponta diretamente para o JSON e evita que o módulo interprete o
`.env` completo do agente. Um host FastAPI incorpora a mesma interface standalone
com `app.mount("/cm/cmail", create_app(config))`, preservando assets, OAuth,
CSRF e rotas sob o prefixo montado.

Estado e dados pessoais ficam em `state.directory/cmail.sqlite3`. Tokens MSAL
e Google ficam em binários DPAPI sob `state.directory/security`. O JSON contém
somente referências para segredo/senha; esses valores nunca ficam no JSON.
Nenhum banco,
usuário, prompt ou regra departamental da LIA foi copiado para o componente.
Veja [ARCHITECTURE.md](ARCHITECTURE.md).
Além de mensagens, a API Python e a aplicação montável expõem anexos, contatos,
diretório e calendário. Alterações externas continuam exigindo confirmação.
Os métodos `system_send` e `invalidate_owner` existem exclusivamente para o host
implementar recuperação de acesso e revogação de credenciais sem manter um
segundo armazenamento de tokens no runtime consumidor.
