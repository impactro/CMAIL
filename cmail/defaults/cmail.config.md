# CMAIL — configuração de conexão e execução

Dono: CMAIL. Schemas aceitos: `1.0`, `1.1`, `1.2`, `1.3`.
Par recomendado: `config/cmail.config.json` / `config/cmail.config.md`, relativo
à instância. Subpastas como `config/cmail/` são permitidas quando registradas
pelo host. Este documento acompanha o JSON, mas não é interpretado como código.

## Fonte efetiva e responsabilidades

O host injeta o caminho JSON em `configFile`. No standalone, `.env` contém
somente `CMAIL_CONFIG_FILE=config/cmail.config.json`. Não há busca automática
por um segundo arquivo nem mesclagem de configurações de conexão. Caminhos
legados explícitos continuam válidos; o catálogo deve informar o caminho real.
O template distribuído com o pacote é uma referência para inicialização e não
é consultado como fallback por uma instância existente.

`Config.from_file` e `Config.from_mapping` são os validadores do módulo.
`CmailConfiguration` permite ao administrador ler, validar, inicializar e
salvar o mesmo arquivo por revisão SHA-256. O host controla quem pode usar
essas operações, registra auditoria administrativa e incorpora o fragmento
`catalog_entry(config_root)` ao catálogo único da composição. O fragmento segue
CES `ces.config.catalog` v1: `cmail.settings`, dono `cmail`, caminhos POSIX
relativos a config/, schema nativo efetivo e applyMode `process-restart` por
padrão. `component-reload` só se o host implementar a reconstrução completa.
Arquivos legados fora de config/ continuam legíveis, mas exigem migração
explícita antes de entrar no catálogo canônico; symlinks são recusados.
O host valida também unicidade de ID/path e o restante do catálogo agregado.
Não publicar essa API como uma
capability de caixa postal nem oferecê-la a usuários comuns.

Instalar o pacote, habilitar CMAIL na instância e conceder acesso/capabilities
a um usuário são três controles distintos, pertencentes ao host. O JSON de
conexão não concede ACL. CMAIL mantém schemas, providers, segredos, OAuth e
vínculo da caixa ao owner; o CWH não deve reimplementar esses mecanismos.

## Schemas e valores

Objetos são fechados: chaves extras e faltantes são recusadas. As seções
obrigatórias existem mesmo quando o provedor correspondente está inativo.
Valores de exemplo/default abaixo são escolhas do template inicial; exceto
os opcionais identificados, campos não são preenchidos por omissão.

| Campo | Tipo / regra | Template inicial |
| --- | --- | --- |
| `schemaVersion` | Texto: `1.0`, `1.1`, `1.2`, `1.3` | `1.3` |
| `mode` | `demo`, `imap`, `microsoft`; desde 1.1 também `setup`, `gmail`; desde 1.2 também `gmail-file` | `setup` |
| `server.host` | Texto: `127.0.0.1`, `localhost`, `::1` | `127.0.0.1` |
| `server.port` | Inteiro 1–65535; porta standalone | 8020 |
| `server.openBrowser` | Booleano; deve ser false em gmail-file | false |
| `server.sessionHours` | Inteiro 1–720 | 12 |
| `server.cookieSecure` | Booleano; usar true quando a origem acessada é HTTPS | false |
| `state.directory` | Caminho não vazio, relativo à pasta deste JSON ou absoluto | `../.state/cmail` |

`server.host` continua loopback mesmo quando o host publica a composição por
proxy HTTPS. Em composição ASGI, o host controla a porta/origem externas;
`server.port` não abre outro servidor CMAIL automaticamente.

| Microsoft (`microsoft`) | Tipo / regra | Template |
| --- | --- | --- |
| `clientId`, `tenantId` | Texto; obrigatórios/não vazios no modo microsoft | vazio |
| `clientSecretFile` | Referência a arquivo externo; obrigatória no modo microsoft | vazio |
| `redirectUri` | HTTPS ou HTTP loopback, termina em `/auth/callback` | vazio |
| `account` | Texto; obrigatório como chave desde 1.1, pode ser vazio para vincular no login | vazio |
| `offlineAccess` | Booleano opcional desde 1.1; opt-in para solicitar renovação Microsoft | false |

Schema 1.0 não aceita `account` nem `offlineAccess` na seção Microsoft.
Alterar `offlineAccess` não renova consentimento existente automaticamente.
O administrador deve verificar o cadastro do aplicativo, consentimento e a
necessidade de novo login; não apagar tokens nem repetir OAuth silenciosamente.

| Google (`google`, obrigatório desde 1.1) | Tipo / regra | Template |
| --- | --- | --- |
| `account` | Texto; pode ficar vazio para vincular no login | vazio |
| `clientId` | Texto; obrigatório/não vazio no modo gmail | vazio |
| `clientSecretFile` | Referência externa; obrigatória no modo gmail | vazio |
| `redirectUri` | HTTPS ou HTTP loopback, termina em `/auth/google/callback` | vazio |

| IMAP/SMTP (`imap`, todos os schemas) | Tipo / regra | Template |
| --- | --- | --- |
| `account`, `username` | Texto; obrigatório/não vazio no modo imap | vazio |
| `passwordFile` | Referência externa; obrigatória no modo imap | vazio |
| `imapHost`, `smtpHost` | Texto; obrigatório/não vazio no modo imap | vazio |
| `imapPort`, `smtpPort` | Inteiros 1–65535 | 993 / 587 |
| `imapSecurity`, `smtpSecurity` | `ssl` ou `starttls` | ssl / starttls |
| `sentFolder` | Texto não vazio com o ID real da pasta de enviados | Sent |

| Gmail por arquivo (`gmailFile`, obrigatório desde 1.2) | Tipo / regra | Template |
| --- | --- | --- |
| `account` | E-mail ASCII; obrigatório/não vazio no modo gmail-file | vazio |
| `tokenFile` | Referência externa a authorized_user; obrigatória nesse modo | vazio |
| `transport` | Obrigatório no schema 1.3: `api` ou `smtp`; schemas anteriores usam api e não aceitam a chave | api |

`gmail-file` é local/headless, via CLI ou `Config.from_file` + `create_api`.
Não pode ser montado como aplicação web nem pela factory de composição.
OAuth Microsoft/Google e IMAP/SMTP continuam sendo providers distintos.

## Referências, segredos e estado

Todos os caminhos relativos são resolvidos pela pasta do JSON, não pelo cwd,
pela pasta do pacote ou por `root` do host. Mover um JSON da raiz para config/
exige ajustar referências relativas para conservar os mesmos destinos.
Não manter a cópia antiga como segunda fonte ativa. O host deve atualizar
`configFile` ou o ponteiro standalone após validar a migração.

Senhas, client secrets e tokens não são valores deste JSON. Armazenar somente
referências a arquivos externos protegidos por permissões do sistema.
Validação de schema não lê segredos, não confirma que existem, não testa rede
nem autoriza a caixa. Caches OAuth são DPAPI sob a área de estado do CMAIL.
Não incluir segredos, conteúdo de mensagens ou estado operacional em Git.

O arquivo aceita até 512 KiB e UTF-8 com ou sem BOM. Gravações administrativas
usam UTF-8 sem BOM. Revisões são SHA-256 dos bytes efetivamente lidos: uma
edição de formatação/BOM já invalida a revisão anterior.

## Aplicação, edição e estado efetivo

As configurações de conexão são carregadas na criação do serviço. Salvar não
reinicia processos, não troca providers nem altera a configuração já em uso.

- Standalone: reiniciar o processo, ou usar o ciclo explícito de recarga já
  oferecido pelo setup local. Alteração de bind/porta requer reabrir o servidor.
- Composição: o host reconstrói o par API/aplicação/serviço ou reinicia seu
  processo. Não conservar API antiga e montar uma aplicação com outro Config.
- Não há watcher, hot reload automático ou callback administrativo nesta API.

`read()` retorna `document`, `revision`, `source`, `saved`, `applied`,
`pendingRestart` e `effective`. Para conhecer
o estado carregado, construir o editor com `from_config(service.config)`.
`matchesSaved` compara semanticamente o JSON validado com esse Config; se o
host não fornecer o Config ativo, o estado efetivo fica desconhecido e se
recomenda restart. `effective.revision` é a revisão exata capturada por
`Config.from_file`; fica null se o Config foi construído de um mapping ou
diretamente, sem um snapshot de arquivo conhecido. Uma edição só de formatação
pode mudar a revisão salva sem mudar os valores efetivos.
Não comprova a versão do pacote, autenticação, estado do
OAuth ou conteúdos atuais dos arquivos referenciados.

`save(document, expected_revision=revision)` exige a revisão lida, valida antes
de gravar, usa lock entre editores cooperantes e substituição atômica do JSON.
Conflito exige releitura e nova revisão humana; não repetir com a revisão nova
automaticamente. Um sidecar `.<nome-json>.lock` permanece para preservar a
identidade do lock. Escritores externos que não seguem esse lock devem ser
serializados operacionalmente pelo host; a checagem extra de revisão não
substitui coordenação com um editor externo arbitrário.

O MD é criado quando ausente e preservado quando já existe, para conservar
notas da instância. `initialize()` cria o par inicial explicitamente no caminho
escolhido e recusa substituir um JSON existente. Não altera `.env`, catálogo
do host, permissões de usuário, credenciais ou estado OAuth. Backups/retention
administrativos pertencem ao host; a API não expurga configuração ou histórico.

## Outros arquivos do CMAIL

Perfil de assinatura/template usa schema 1.0 e leitura dinâmica por render.
As localizações operacionais atuais (`mail/company/profile.json`, perfil
pessoal e `<workspace>/mail/profile.json`) continuam compatíveis; não foram
movidas nem copiadas para config/ nesta extensão da conexão. O host deve
registrar seus caminhos efetivos quando oferecer edição desses perfis e
planejar uma migração única, sem criar fontes concorrentes. Não são prompts.

Preferências de webmail, journal, sessões e auditoria ficam no SQLite e não
se tornam arquivos genéricos de configuração. Não há prompts de IA próprios
carregados pelo CMAIL. O catálogo do host deve distinguir esses dados dos
arquivos JSON/MD de configuração e dos prompts pertencentes ao CWH/CA.
