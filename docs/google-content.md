# Conteúdo Google pelo CMAIL

## Intenção e responsabilidade

O CMAIL é dono da integração Google reutilizável: autenticação, consentimento,
vínculo do proprietário e operações de conteúdo. O host autentica o usuário e
fornece um Principal; não copia tokens nem implementa outro cliente Google.
Gmail autorizado não implica acesso ao Drive, Docs, Sheets ou Slides.

## Procedimento de implementação e validação

1. Reutilizar GoogleAuthService e o armazenamento protegido existente. Publicar
   os escopos exigidos por capacidade e solicitar consentimento incremental
   apenas por ação explícita, nunca durante uma consulta.
2. Acrescentar API pública de conteúdo com capacidades de leitura e escrita
   distintas, sempre vinculadas ao proprietário da identidade Google.
3. Oferecer busca paginada e metadados do Drive e operações delimitadas de
   conteúdo de Docs, Sheets e Slides. Limitar respostas, páginas e entradas.
4. Alterações exigem prévia vinculada ao proprietário e execução confirmada;
   erros após início da escrita são incertos e não autorizam repetição.
5. Publicar operações e skill no descritor CM. O CA continua adaptador: resolve
   identidade e capacidades, sem reimplementar OAuth nem APIs dos provedores.
6. Testar com respostas HTTP simuladas: isolamento entre proprietários,
   escopos ausentes, paginação, limites, falhas, prévia sem escrita e execução
   única. Executar também as regressões existentes de email.

## Limite de homologação deste ambiente

Não existe caixa de email integrada para homologação real. Testes simulados
comprovam contratos e regressões locais, não conexão Google, consentimento de
uma conta real nem envio/recebimento de email. A instalação deve informar essa
diferença. Não criar credenciais de cliente nem iniciar login automaticamente.

## Fontes oficiais

- [Consentimento incremental](https://developers.google.com/identity/protocols/oauth2/web-server#incrementalAuth)
- [Drive API](https://developers.google.com/workspace/drive/api/reference/rest/v3)
- [Docs API](https://developers.google.com/workspace/docs/api/reference/rest)
- [Sheets API](https://developers.google.com/workspace/sheets/api/reference/rest)
- [Slides API](https://developers.google.com/workspace/slides/api/reference/rest)

O contrato e os resultados abaixo distinguem testes simulados de homologação real.

## Contrato implementado — CES 26.11.2a / Python 26.11.2

Tasks12/13: CMAIL implementa o cliente genérico; o adaptador CA fica com o
integrador. Não há dependência de CA, identidade departamental ou configuração
produtiva neste código. Nenhum token sai da autenticação do módulo.

### Autenticação, autorização e consentimento

- Reutiliza **GoogleAuthService**, o mesmo Store e os binários DPAPI existentes
  em `state.directory/security/google/tokens`, dentro da área persistente
  `security/cmail/` resolvida pelo Config. Não cria diretório de segredos paralelo.
- Cada operação exige Principal com identity_id Google persistido, conexão
  autorizada e `Principal.storage_owner == (identity.owner_id or identity.id)`.
  Esse teste precede leitura de token, refresh e HTTP. O owner vazio legado usa
  o ID real da identidade como storage_owner; não significa conta compartilhada.
- O host autentica sua assertion antes de chamar
  `api.google_content_principal_for_owner(owner_verificado, frozenset(capacidades_permitidas))`.
  Esse método é uma interface confiável de host, **não** deve ser exposto como
  ferramenta para aceitar owners/capacidades arbitrários do modelo ou usuário.
- Capacidades são independentes: `google.drive.read/write`,
  `google.docs.read/write`, `google.sheets.read/write`, `google.slides.read/write`.
  `.write` no Principal não concede `.read`. Escopo OAuth pleno, por sua vez,
  satisfaz seu equivalente `.readonly`, mas não a capacidade ausente do host.
- Escopos de leitura: `https://www.googleapis.com/auth/` mais `drive.readonly`,
  `documents.readonly`, `spreadsheets.readonly`, `presentations.readonly`.
  Escrita usa os respectivos escopos sem `.readonly`. Drive genérico exige
  acesso amplo aos arquivos da conta, não apenas `drive.file`; o host deve
  explicar esse alcance na autorização. Gmail nunca satisfaz esses escopos.
- Cada consulta e prévia verifica o grant real no token protegido, nunca supõe
  que escopo solicitado foi concedido. Ausência gera
  `cmail.ConsentRequired`, mensagem `consent-required`, atributo `.scopes`.
  Não abre navegador nem inicia OAuth. Leituras podem renovar silenciosamente
  **um grant já existente**; o escopo é novamente verificado após o refresh.
- Ação explícita do usuário: `api.google_content_begin_consent(principal,
  capability)` retorna `(authorization_url, browser_nonce)`, sem HTTP ou browser.
  A URL contém `include_granted_scopes=true`, `prompt=consent`, `openid email`
  e somente o escopo adicional da capacidade selecionada. O host protege o
  nonce/state em sua sessão autenticada e promove a URL fora de iframe.
- Callback na **mesma CmailApi que iniciou o fluxo**:
  `api.google_content_complete_consent(response_dict, browser_nonce, stored_owner_id)`.
  `stored_owner_id` vem da sessão autenticada, nunca da query; para identidade
  standalone legada é `""`, não `Principal.storage_owner`. Retorna
  o estado da identidade e `authorizedCapabilities` efetivamente concedidas,
  sem tokens OAuth ou cookies de sessão. Não autentica o navegador no Webmail.
  State/nonce são de uso único e expiram conforme o OAuth existente. O callback
  compara subject e owner originais antes de persistir, sem chamada Gmail no
  fluxo incremental; refresh_token omitido é preservado só da mesma identidade.
  Escopos omitidos não são inferidos. O host deve revalidar sua assertion e
  política também no callback. Reinício perde fluxos pendentes: iniciar nova
  ação explícita. Callback OAuth não pode ser executado em um worker diferente
  sem roteamento de sessão ao serviço iniciador.
- `begin()` legado continua solicitando GMAIL_SCOPES e verificando `/profile`.
  Microsoft Graph, Gmail por arquivo e IMAP preservam seus fluxos próprios.
- **Conteúdo sem caixa de email:** Google pode ser configurado junto de outro
  modo do CMAIL. Configurar explicitamente clientId, referência do segredo e
  redirectUri na seção Google existente. O host inicia a autorização com
  `Principal('', '', frozenset({capacidade_google}), owner_verificado)`; exige
  owner e capacidade afirmados pelo host. Não solicita escopos Gmail nem chama
  a API de caixa postal. Se já existe identidade Google desse owner, ela fica
  vinculada ao mesmo subject. Novo vínculo exige refresh_token; consentimento
  incremental preserva somente o refresh da identidade comprovada. Uma conta
  explicitamente fixada em google.account continua sendo respeitada.
  Resolver depois com `google_content_principal_for_owner`, nunca pelo provedor
  de email configurado. Não há conexão automática durante uma consulta.

### API pública tipada e allowlist

Imports públicos: `CmailApi`, `GoogleRead`, `GoogleWrite`, `ReadOperation`,
`WriteOperation`, `ConsentRequired`, `Principal` de `cmail`.

`api.google_content_read(principal, GoogleRead(operation, ...))`:

| ReadOperation | Campos | Resultado |
| --- | --- | --- |
| DRIVE_LIST (`drive.list`) | query="", page_token="", page_size=100, max_pages=1 | files, nextPageToken, incompleteSearch, complete |
| DRIVE_GET (`drive.get`) | identifier | metadados id/name/mimeType/description/parents/modifiedTime/size |
| DRIVE_TEXT (`drive.text`) | identifier, export=False | objeto `text`; text/plain, ou Docs exportado se export=True |
| DOCS_GET (`docs.get`) | identifier | documento JSON |
| SHEETS_GET (`sheets.get`) | identifier, range="A1:Z100" | valores JSON, não workbook inteiro |
| SHEETS_METADATA (`sheets.metadata`) | identifier | abas e metadados dos gráficos, sem dados da grade |
| SLIDES_GET (`slides.get`) | identifier | apresentação JSON |

Lista aceita query Drive, sem URL fornecida pelo chamador. nextPageToken é a
única indicação de outra página: página vazia/parcial não encerra a consulta.
No limite retorna cursor para continuação explícita; `complete` é falso com
cursor ou incompleteSearch. Cursor repetido falha, sem loop. Sem ordenação
implícita ou promessa de snapshot consistente entre páginas.

`api.google_content_prepare(principal, GoogleWrite(operation, identifier="",
changes={...}))` aceita somente:

| WriteOperation | changes permitidos |
| --- | --- |
| DRIVE_UPDATE (`drive.update`) | name e/ou description; não move, compartilha ou exclui |
| DRIVE_FOLDER (`drive.create_folder`) | name, parent opcional; identifier não é usado |
| DOCS_BATCH (`docs.batch_update`) | requests com insertText: text e location.index (1..1000000) |
| SHEETS_UPDATE (`sheets.update`) | range, values (até 100 linhas x 26 células); valueInputOption=RAW |
| SHEETS_FORMAT (`sheets.format`) | sheetId, start/endRowIndex, start/endColumnIndex, format; até 100×26 células |
| SLIDES_BATCH (`slides.batch_update`) | requests com insertText: text, objectId, insertionIndex (0..1000000) |

Campos desconhecidos e outros comandos batch são recusados. Cada lote tem
1..20 inserções; texto até 10000 caracteres por inserção. Não oferece exclusão,
sharing, upload binário, links remotos ou proxy arbitrário. Docs usa **POST
`https://docs.googleapis.com/v1/documents/{id}:batchUpdate`**. A faixa Sheets
é codificada no path e valores RAW não interpretam fórmulas.
Formatação permite bold/italic booleanos, fontSize6..72, alinhamento
LEFT/CENTER/RIGHT e numberFormat com tipo enumerado e pattern até80 caracteres.
O módulo monta repeatCell e uma máscara dos campos explícitos; não aceita
batch livre, `*`, exclusão de abas ou alteração dos valores como formatação.

### Escrita em duas fases e consumo atômico

1. `google_content_prepare` valida e congela o conteúdo, owner, capacidade e
   escopos localmente. **Não renova token nem faz HTTP**, mesmo com token de
   acesso expirado. Retorna `previewId`, `confirmationToken`, `expiresAt` (Unix
   UTC), `preview` (snapshot exato), `status="prepared"`.
2. Host apresenta todo o snapshot, alvo e alcance, colhe confirmação humana
   específica, mantém token fora de logs/prompts e chama:
   `api.google_content_execute(principal, preview_id, confirmation_token,
   confirmed=True)`. Não aceita substituição de conteúdo nesta chamada.
3. SQLite `BEGIN IMMEDIATE` verifica owner + identidade + hash do token + prazo
   + status, e persiste `claimed` **antes** de refresh/HTTP. Capacidade/grant
   ausente antes do claim não consome a prévia e não faz HTTP.
4. Resultado: `{previewId, status: "completed"|"uncertain", result,
   retryAllowed: False}`. Falha de transporte, HTTP não-2xx, resposta inválida
   ou acima do limite após claim é conservadoramente `uncertain`, com
   `result.error="google-write-uncertain"`. Nem HTTP 4xx autoriza retry.
5. Replay, execução concorrente e execução após reinício são recusados quando
   já claimed/completed/uncertain. Crash após claim também consome, mesmo sem
   registro de resposta. O host deve persistir o recibo de execução; não há
   método de consulta pública do journal nesta fatia. Resultado incerto exige
   revisão remota autorizada, nunca repetir ou criar nova prévia automaticamente.

Prévias vivem na tabela `google_content_previews` do **mesmo cmail.sqlite3**,
com payload e hash, não o token de confirmação. Expiram em 600s; limpeza de
expiradas ocorre ao preparar. Limite de 128 registros não expirados por owner.
Esse limite inclui consumidos, como proteção de taxa local. Conteúdo sensível
permanece no estado privado existente; o journal não deve ir para Git/logs.

### Limites e tratamento de dados

IDs: ASCII opaco `[A-Za-z0-9_-]{1,256}`, sem caminho/URL. Consulta/cursor até
2048 caracteres, range até 256, nome até 255 e descrição até 4096.
Entrada JSON até 64 KiB. Transporte lê incrementalmente até 1 MiB e valida
novamente o tamanho serializado inclusive no requester injetado. Agregado de
arquivos de uma listagem também limitado a 1 MiB. Excesso falha, não trunca
silenciosamente. Documentos/apresentações grandes não são suportados aqui.

Até 100 itens/página e 10 páginas/chamada. Transporte sem redirects e sem
retries, timeout de socket 20s e deadline cooperativo de leitura 20s, verificado
entre chunks; listagem verifica deadline cooperativo 60s entre páginas. Não é
cancelamento hard-real-time: operação de socket já em curso pode exceder o
deadline até seu timeout. Refresh OAuth usa os limites existentes (20s e leitura
limitada). O host deve executar API síncrona fora do loop ASGI e aplicar sua
própria política de job/deadline sem reexecutar escritas canceladas.

Erros de transporte/resposta não publicam corpo Google, URL, cabeçalhos ou
exceção original. Respostas e texto Google são dados não confiáveis, não
instruções. O host continua responsável por renderização segura, retenção e
não enviar conteúdo privado a prompts sem autorização.

### Exemplo de adaptação CA (somente contrato; não executado contra Google)

```python
from cmail import GoogleRead, GoogleWrite, ReadOperation, WriteOperation

# auth_owner e allowed_caps vêm da assertion validada e da política do host.
p = api.google_content_principal_for_owner(auth_owner, frozenset(allowed_caps))
page = api.google_content_read(p, GoogleRead(
    ReadOperation.DRIVE_LIST, query="trashed = false", max_pages=2))
# Expor nextPageToken; nunca declarar lista completa se complete=False.
preview = api.google_content_prepare(p, GoogleWrite(
    WriteOperation.DRIVE_UPDATE, identifier=selected_file_id,
    changes={"name": approved_name}))
# Mostrar preview['preview']; somente após confirmação específica:
receipt = api.google_content_execute(
    p, preview['previewId'], preview['confirmationToken'], confirmed=True)
```

O adaptador traduz ferramentas tipadas para esses DTOs, não para URLs. Captura
ConsentRequired e oferece ação separada de consentimento; não tenta login como
tratamento automático da consulta. Não toma `storage_owner`, capabilities ou
identity_id de argumentos do modelo. Revalidar identidade/política a cada ação,
inclusive entre prévia e execução. Não copiar ou administrar o cache Google.

CM 2 oferece `google-content-contract` executável sem Config, somente descoberta
JSON. Leitura, preparação e execução são selecionáveis separadamente por
`google-content-read`, `google-content-prepare`, `google-content-execute`; esses
IDs são operações da API para os adaptadores autenticados, sem CLI de identidade.
A skill empacotada `google-content` descreve as operações da API. As
operações reais **não** são expostas como CLI/JSON porque a CLI não autentica
assertion de host. `Principal.local_operator()` não tem vínculo Google e é
recusado, não elevado implicitamente. Não há novo endpoint HTTP público nem UI
para conteúdo/consentimento: o integrador implementará a composição autorizada.

### Evidência local e pendências

Validação com Python 3.12 global, `PYTHONNOUSERSITE=1` e `-s`, dependências já
instaladas, fixtures sintéticas e todos os transportes Google simulados.
Resultados e comandos finais registrados abaixo após execução. Os testes
comprovam isolamento, grants, paginação, limites, prévia sem HTTP, claim
concorrente/durável, replay, falha incerta consumida e regressões de email.
**Email real, login/consentimento e conta Google real não homologados aqui.**
Nenhum acesso produtivo, browser, OAuth real, envio, instalação global, commit
ou push fez parte desta validação.

Comandos reproduzíveis (PowerShell, na raiz CMAIL; resolução local do Python312 global):

```powershell
$python = (Get-Command python).Source
$env:PYTHONNOUSERSITE='1'
& $python -s -m pytest -q -p no:cacheprovider tests/test_google_content.py --basetemp=.agents/temp/google-content-check
# 65 testes de conteúdo, inclusive conexão sem caixa postal e formatação.
& $python -s -m pytest -q -p no:cacheprovider --ignore=tests/test_appearance_browser.py --ignore=tests/test_frontend_playwright.py --basetemp=.agents/temp/google-regression-check
# 303 testes aprovados; inclui regressões Gmail/Graph/IMAP.
& $python -s -c "from setuptools.build_meta import build_wheel; print(build_wheel('dist'))"
# crania_cmail-26.11.2-py3-none-any.whl; sem instalação e sem resolução de dependências.
```

A execução usou Python 3.12 global, sem user-site ou instalação. O build emitiu somente
FutureWarning do wheel/setuptools já instalado. A skill e o módulo Google estão
no wheel. `dist/`, `build/`, egg-info e fixtures de execução não integram a entrega
Git. Testes de browser foram deliberadamente excluídos; nenhum browser aberto.
