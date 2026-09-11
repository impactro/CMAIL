# CMAIL

`CMAIL` é o nome técnico do módulo independente que reúne webmail, leitura de
pastas e mensagens, listas de destinatários e disparo controlado de e-mail.
Versão do componente: `26.9.11a` (pacote Python `26.9.11a0`).

## Execução

O modo inicial `demo` abre toda a interface, mantém listas e simula a aceitação
sem rede. Para usar uma conta real, configure `CMAIL_MODE=imap`, os endpoints
IMAP/SMTP e `CMAIL_PASSWORD_FILE`, sempre apontando para arquivo externo ao Git.

```powershell
python -m cmail check-config
python -m cmail status
python -m cmail list-folders
python -m cmail list-messages --folder INBOX --limit 50
python -m cmail serve
```

Dependências declaradas: Flask 3.x e Waitress 3.x. Para validar o checkout e
construir o wheel sem instalar no host:

```powershell
python -m pytest -q
python -m pip wheel . --no-deps --wheel-dir dist
```

`serve` usa Waitress e abre `http://127.0.0.1:7420/`. A versão inicial aceita
IMAP/SMTP com SSL ou STARTTLS. Corpos HTML são convertidos em texto antes de
chegar à interface; imagens remotas não são carregadas. Anexos são apenas
inventariados nesta primeira ejeção.

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

Estado e dados pessoais ficam em `CMAIL_STATE_DIR/cmail.sqlite3`. Nenhum banco,
usuário, prompt ou regra departamental da LIA foi copiado para o componente.
Veja [ARCHITECTURE.md](ARCHITECTURE.md).
