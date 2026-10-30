# Migração de configuração existente e bootstrap sem caixa

Referência de runtime: `a6e1088`, CMAIL `26.10.30c`, pacote
`26.10.30.post2`. A API administrativa existe desde `5fee2f6`, pacote
`26.10.30.post1`; o patch post2 corrige descoberta em `dir(cmail)`/`__all__`.
O hotfix remoto `23dcf9e` / 26.10.30d / `26.10.30.post3`, incorporado nesta
documentação, conserva essa API e corrige a resposta Graph 201 ao mover e-mail.
Esta nota não autoriza operação remota, instalação ou escolha de conta.

## Inventário que o operador precisa

Antes de criar algo, identificar a raiz operacional da instância, seu principal
de serviço Windows e o caminho realmente entregue ao módulo. Consultar o
catálogo `cmail.settings`, o `host_services.configFile` efetivo ou, somente no
standalone, `CMAIL_CONFIG_FILE` do `.env` dessa raiz. Não usar fixtures/testes
de outro agente como configuração real. Não alterar o `.env` técnico do CA.

Não há descoberta nativa de workspace, Gmail, Outlook ou credenciais externas.
`Config.load(root)` lê somente o ponteiro standalone; `Config.from_file` lê
somente o arquivo escolhido. `mailWorkspaceRootResolver` resolve aparência
pessoal e não procura caixa postal. Habilitar o componente no host não escolhe
provider nem comprova que exista uma configuração válida.

O inventário abaixo é de referências e ownership. Não abrir os arquivos de
segredo/token, não exportar seu conteúdo e não copiar credenciais para JSON/MD.

| Referência no JSON | Destino que precisa permanecer o mesmo |
| --- | --- |
| `state.directory` | Estado SQLite, journal, sessões, identidades e caches OAuth |
| `microsoft.clientSecretFile` | Arquivo externo do segredo Microsoft |
| `google.clientSecretFile` | Arquivo externo do segredo Google |
| `imap.passwordFile` | Arquivo externo da senha IMAP/SMTP |
| `gmailFile.tokenFile` | Arquivo authorized_user explícito do modo headless |

As seções Google/GmailFile só existem nos schemas que as suportam. Rebater
também referências preenchidas de providers inativos, preservando futura troca.
Referência vazia continua vazia. Não criar seções ausentes nem trocar o schema
para o mais recente durante uma simples mudança de pasta.

## Mover um JSON válido para config/

1. O operador registra o JSON efetivo, revisão, versão do pacote carregado,
   raiz operacional e destinos resolvidos das cinco referências. Guarda backup
   protegido, sem torná-lo segunda fonte gerida. Pausa editores concorrentes.
2. Lê o JSON com `CmailConfiguration.from_config(service.config).read()` ou
   valida o arquivo com `Config.from_file(old_path, root=instance_root)`.
   Leitura/validação não precisam abrir segredo ou iniciar OAuth.
3. Prepara `config/cmail.config.json` e seu MD, conservando todos os campos
   nativos. Caminhos relativos são relativos à pasta do JSON, nunca a `root`:
   calcular cada destino pelo diretório antigo e expressá-lo relativamente ao
   diretório novo. Se os drives forem diferentes, usar a referência absoluta
   permitida pelo contrato; não trocar o destino. Não imprimir caminhos privados
   em um log público.
4. Valida em memória com
   `Config.from_mapping(candidate, path=new_path, root=instance_root)`. Compara
   os campos do Config antigo e novo, exceto `config_file` e `source_revision`.
   Devem coincidir, incluindo mode/schema, contas, flags, redirects, protocolos,
   portas, transport, state e referências. Não chamar `password()`, métodos de
   client secret, `access_token()`, setup/save de provider ou operações de rede.
5. O host persiste o candidato validado e MD usando seu procedimento protegido,
   registra uma única entrada de catálogo e troca `configFile`/ponteiro. O módulo
   não tem método de migração que mova esses arquivos automaticamente.
6. Reconstrói o par API/ASGI/serviço ou reinicia pelo trilho operacional do host.
   Com o novo `service.config`, verifica `read().effective` e que o caminho/revisão
   carregados correspondem ao destino. Só depois retira a cópia anterior da
   gestão ativa. Rollback restaura o ponteiro e o par anteriores; não apaga estado.

Preservar `root=instance_root` é obrigatório: sem ele, o default de `from_file`
vira a pasta do JSON novo e pode mudar `mail/company`/`mail/personal`.
O helper `initialize()` não migra e não deve substituir um JSON existente.
`SetupService.save()` também não é um migrador: ele configura provider/segredo
e pode resetar vínculos OAuth. Não utilizá-lo nessa passagem.

## Estado, identidade e composição

Manter o destino de state preserva a localização de `cmail.sqlite3`, seu
WAL/SHM, journal, preferências, sessões, vínculos por owner e caches em
`security/`. Não renomear ou reescrever tabelas/IDs. Tokens DPAPI continuam
dependendo da identidade Windows que os protegeu: mover somente o JSON não
autoriza troca de usuário de serviço ou de máquina.

Conservar `principalResolver`/`principalResolvers`, owner/workspaceId e
capabilities fornecidos pelo host; `mailCompanyRoot` e
`mailWorkspaceRootResolver`; `registerOAuthCallback`, `oauthSuccessPath`,
redirectUri e prefixo ASGI. Uma mudança de origem/callback ou de conta é outra
operação, com validação/autorização própria. Não fazer login/reconectar apenas
para testar uma mudança de path e não enviar e-mail como teste implícito.

Perfis de aparência atuais são schema 1.0 e permanecem onde já estão:

- Empresa: `mailCompanyRoot` explícito ou `<instance_root>/mail/company/profile.json`.
- Standalone: `<instance_root>/mail/personal/profile.json`.
- Resolver: `<workspace>/mail/profile.json`.
- Fallback com owner: `<state>/workspaces/<hash-do-owner>/mail/profile.json`.

HTML e assets continuam relativos à pasta de cada perfil. Esses perfis ainda
não foram migrados para config/ e não devem ganhar cópias concorrentes.
O módulo não tem prompts IA próprios. SQLite, caches OAuth e estado de envio
não são arquivos JSON de configuração para registrar como editáveis.

## Não existe configuração: bootstrap administrativo

Se a inspeção dos apontamentos efetivos confirmar ausência de uma configuração
anterior para esta instância, o administrador pode usar o template oficial:

```python
from cmail import CmailConfiguration
from cmail.api import create_component_api

editor = CmailConfiguration(instance_root / "config" / "cmail.config.json",
                            root=instance_root)
snapshot = editor.initialize()  # Create-only; falha se o JSON já existir.
api = create_component_api(instance_root, {"configFile": editor.path})
```

O resultado usa schema 1.3 e `mode=setup`, contas/segredos vazios,
`offlineAccess=false` e `openBrowser=false`. Não seleciona Outlook/Gmail/IMAP,
não associa caixa, não cria SQLite, não muda `.env`/catálogo nem busca arquivos
de credenciais existentes. O state default é `../.state/cmail` relativo ao JSON;
se já houver um destino de estado operacional conhecido, não adotá-lo como
substituto sem conciliação. Fonte desconhecida não equivale a instância nova.

Factories Python e ASGI aceitam setup. A API existe, mas operações de caixa
ficam bloqueadas e `/health` informa `configured=false`. Isso é diferente de
um host que não encontrou o JSON e acusou `CM_API_NOT_CONFIGURED`.
Não mudar para demo para mascarar esse diagnóstico.

O formulário nativo `/setup` é **somente standalone** e devolve 404 quando
há `principalResolver`. A raiz em setup redireciona para ele; portanto não
anunciar o webmail embutido como pronto nessa fase. O painel administrativo
do CA/CWH deve apresentar a configuração pelo provider do host, usar
`CmailConfiguration.read/validate/save(expected_revision=...)`, provisionar
referências de segredo pelo trilho autorizado e aplicar reload/restart.
Não remover o principal para liberar o setup nem usar sessão comum como admin.

## Evidências e limites

`tests/test_configuration_migration.py` usa schemas 1.0–1.3 e referências
sintéticas de IMAP, Microsoft, Gmail e Gmail-file API/SMTP. Compara todos os
valores efetivos e raízes de aparência antes/depois de mudar a pasta do JSON,
sem criar estado ou abrir segredos. Também confere bootstrap setup nas duas
factories, bloqueio da API e 404 do setup embutido.

Isso não comprova configuração/OAuth em uma máquina real. O DEV/OPS responsável
deve registrar versão realmente importada, paths efetivos, status do host e
ausência de regressão de identidade/caixa depois da aplicação autorizada.
