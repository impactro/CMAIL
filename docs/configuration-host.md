# Configuração administrativa pelo host

## Onboarding Gmail hospedado

Desde CMAIL26.11.3a/Python26.11.3, `create_app` aceita `setup_authorizer`
(callback síncrono Request→bool) e `setup_origin` (origem explícita confiável).
Na factory CM, os nomes são `setupAuthorizer` e `setupOrigin` em host_services.
São opcionais; sem authorizer, `/setup` hospedado continua404. O host deve
conferir sessão humana, papel administrador e alcance da instância em CADA
chamada antes de retornar exatamente True. Uma capacidade mail.manage ou uma
credencial MCP não comprovam essa autorização. O principalResolver existente
é preservado e também consultado; não é necessário estar conectado ao Gmail.

Exemplo de composição (o host implementa a autorização, sem roles inferidos):

```python
create_app(config, principal_resolver=resolve_mail_owner,
           setup_authorizer=authorize_current_human_admin,
           setup_origin="http://localhost:2670")
```

A montagem canônica CAW/CWH é `/cm/cmail`, com callback
`http://localhost:2670/cm/cmail/auth/google/callback` neste exemplo.
Domínio e porta variam por consumidor; o caminho permanece
`/cm/cmail/auth/google/callback`. A origem vem do host,
nunca de Host, query ou do arquivo importado. Não incluir caminho/barra final
em setup_origin. HTTPS ou HTTP loopback são aceitos; o host deve usar a mesma
origem no navegador para conservar sua sessão. Registrar o callback exato
no cliente Google Web antes da importação.
O módulo conserva suporte técnico a outros prefixos ASGI, inclusive o antigo
`/email` do CWH; isso não o torna o caminho canônico. A mudança de montagem,
links, configuração e registro OAuth pertence ao host, preservando os callbacks
existentes de outros consumidores até migração explícita.

O formulário `/setup` é inicial-only (`mode=setup`) e protegido por CSRF de
sessão próprio e revisão CAS. Aceita upload multipart `oauthClientFile` de
até64KiB; formulário inteiro até96KiB. Somente JSON com raiz `web`, client_id,
client_secret e callback em redirect_uris. Tokens/authorized_user/installed
são recusados; URLs de autorização do arquivo não são usadas. O segredo não
é devolvido à UI: arquivo UUID com ACL restrita em state/security/google,
referência no JSON. Não cria caixa, scheduler ou sessão OAuth nem reseta grants.

O POST retorna202 HTML: salvo, mas aplicação/reinício do host pendente.
Nenhum restart_callback é chamado nesse modo. A configuração ativa permanece
setup até o operador recriar o componente. Após aplicar, `/connection` oferece
Conectar Gmail, com consentimento na janela principal e owner do host pelo
fluxo nativo existente. Reconfiguração de caixa já configurada fica fora deste
onboarding e retorna409; não usar setup para reparar ou transferir contas.

Fixtures não comprovam cadastro do aplicativo, consentimento Google real ou
leitura da caixa no consumidor. Não houve alteração de CWH/CA ou instalação
de runtime por esta entrega. CCI/anotações não fazem parte deste contrato.

Componente `26.10.30c`, distribuição `26.10.30.post2`. Continuação aditiva da
refatoração `088b427` / `26.10.30a`, para configuração pelo CWH/CA e standalone.
Não inclui instalação, migração de instâncias existentes ou implementação no CWH.

## Arquivo, documentação e catálogo

Novas instâncias adotam `config/cmail.config.json` e
`config/cmail.config.md`. O host pode usar subpasta por módulo. Um único JSON
efetivo é injetado por `configFile`; não existe autodiscovery nem merge de
arquivos de conexão. O standalone usa somente o ponteiro `CMAIL_CONFIG_FILE`
no `.env`. Referências relativas continuam resolvidas pela pasta do JSON.

O destino padrão do estado é `security/cmail/` na raiz da instância:
`state.directory=../security/cmail` para o JSON em `config/`.
Seguir o [padrão de armazenamento e migração](state-storage.md), inclusive
para migrar uma instalação que ainda usa `.state/cmail/`.

O pacote inclui `cmail/defaults/cmail.config.json` e seu MD: são o par inicial,
schema 1.3, modo setup e referências vazias. `initialize()` copia esses valores
para o caminho explícito da instância; o pacote não vira uma segunda fonte
ativa. A [documentação distribuída](../cmail/defaults/cmail.config.md) descreve
todos os campos, versões, valores iniciais, referências e aplicação.

`catalog_entry(config_root, consumers=(...), apply_mode=...)` devolve uma
entrada no contrato `ces.config.catalog` v1, definido pelo CServer em
`CES/padroes/config-catalog.schema.json` e seu MD. O host agrega essa entrada
em seu catálogo único, sem copiar valores do CMAIL para outro JSON:

```json
{
  "id": "cmail.settings",
  "moduleId": "cmail",
  "path": "cmail.config.json",
  "documentation": "cmail.config.md",
  "schemaVersion": "1.3",
  "purpose": "Provedor, servidor, referências de segredo e estado do CMAIL.",
  "consumers": ["cmail", "cwh"],
  "applyMode": "process-restart",
  "editable": true,
  "sensitive": false,
  "secretPaths": []
}
```

O fragmento usa schema nativo efetivamente salvo; suporta 1.0 a 1.3. Caminhos
são POSIX relativos à pasta config selecionada, com MD de mesmo nome-base.
Rejeita arquivo fora dessa pasta, symlinks/aliases e MD ausente. O host continua
responsável por validar schema, campos desconhecidos, IDs/paths duplicados e
escapes no catálogo completo, inclusive entradas fornecidas por outros módulos.
`secretPaths` está vazio porque o JSON nativo só permite referências externas;
isso não dispensa a autorização administrativa nem a proteção dos arquivos.
O campo CES `optional` pode ser omitido: o JSON de conexão é obrigatório e não
tem contrato de recuperação pela ausência. `next-operation` existe no catálogo
comum, mas a conexão CMAIL conserva reload/restart; não se aplica ao provider
ativo no meio de uma operação.

## API Python de administração

```python
from pathlib import Path
from cmail import CmailConfiguration, ConfigurationConflict

instance_root = Path("instance").resolve()
config_file = instance_root / "config" / "cmail.config.json"

# O host já validou autorização administrativa. Inicialização é explícita,
# somente em uma instância nova, antes de construir seu serviço.
editor = CmailConfiguration(config_file, root=instance_root)
initial = editor.initialize()  # Recusa substituir um JSON existente.

# Em uma instância já em uso, obtenha o Config do serviço ativo:
# editor = CmailConfiguration.from_config(api.service.config)
snapshot = editor.read()
candidate = snapshot["document"]
candidate["server"]["port"] = 8021
validated_config = editor.validate(candidate)  # Não grava ou lê segredos.
try:
    result = editor.save(candidate, expected_revision=snapshot["revision"])
except ConfigurationConflict:
    # Mostrar conflito; reler e submeter a nova revisão ao administrador.
    # Não repetir automaticamente a edição sobre os valores novos.
    raise

entry = editor.catalog_entry(instance_root / "config", consumers=("cmail", "cwh"))
```

`validate()` retorna o Config imutável validado, para uso interno pelo host.
O painel/skill pode receber somente o resultado de validação e mensagens de
erro, sem expor métodos de acesso a segredos. `ConfigurationConflict` deriva
de `ConfigError`: o adapter do host pode traduzi-lo para HTTP 409; erros de
validação podem virar HTTP 400. Não foram adicionadas rotas HTTP no CMAIL.

As factories públicas `create_api`, `create_component_api`, `create_app` e
`create_component_app` permanecem compatíveis. Serviços de composição
`configFile`, `principalResolver`/`principalResolvers`, `mailCompanyRoot` e
`mailWorkspaceRootResolver` continuam sendo injetados pelo host. O principal
autenticado define owner/capabilities por request; nunca vem do JSON de conexão.

## Concorrência, segurança e falhas

A revisão SHA-256 corresponde aos bytes lidos, inclusive BOM/formatação.
Arquivos têm até 512 KiB. Leitura é limitada, e validação reutiliza
`Config.from_mapping`, o mesmo parser de `Config.from_file`, com as mesmas
regras de paths. Nem validação nem save contactam providers, leem senhas,
renovam OAuth, criam SQLite, revogam identidade ou enviam e-mail.

Save usa lock no processo e sidecar entre processos, arquivo temporário no
mesmo diretório, flush/fsync e `os.replace`. Validação ou falha de replace
preserva o JSON anterior; seu temporário é removido. O sidecar permanece para
não trocar a identidade do lock. Escritores externos arbitrários, incluindo
editores manuais e o setup legado, devem ser serializados pelo operador/host.
A API faz uma segunda comparação antes de substituir, mas não oferece CAS
atômico contra um escritor externo que ignore o lock.

O MD é criado se ausente e preservado se já existe. Backups, auditoria de quem
editou e retenção administrativa pertencem ao host. Inicialização cria o par
antes da ativação; não equivale a uma transação de dois arquivos nem altera o
catálogo/.env. Se uma falha interromper a inicialização, verificar o par antes
de ativar o componente. Nenhuma instalação existente é movida silenciosamente.

## Salvo, aplicado e restart

`read()`, `save()` e `initialize()` retornam:

| Campo | Significado |
| --- | --- |
| `document` | Snapshot do JSON nativo, com referências, sem conteúdo de segredos |
| `revision` | SHA-256 dos bytes desse arquivo salvo |
| `source` | Paths reais, documentação disponível e modos de aplicação suportados |
| `saved` | true: há um snapshot persistido |
| `applied` | Igualdade semântica com o Config fornecido; null se desconhecido |
| `pendingRestart` | true quando diverge ou quando o estado ativo não é conhecido |
| `effective.known` | O host forneceu um Config ativo desta mesma instância/arquivo |
| `effective.matchesSaved` | Igualdade semântica entre arquivo validado e Config ativo |
| `effective.revision` | Revisão exata capturada ao carregar o Config de arquivo; null quando indisponível |
| `effective.schemaVersion`, `effective.mode` | Valores carregados no serviço fornecido |

Use `CmailConfiguration.from_config(service.config)` para estado efetivo. Se o
host apenas abrir um path, a API não presume que ele esteja ativo. Revisão de
formatação pode diferir mantendo `matchesSaved=true`; isso não exige trocar
provider. Config criado diretamente/de mapping não tem revisão de arquivo,
mas ainda permite comparar os valores. Conteúdo de segredos referenciados,
versão do pacote e autenticação não são comprovados por essa igualdade.

Conexão/servidor/state usam `process-restart` por padrão. Um host que implemente
reconstrução completa do par API/ASGI/serviço pode declarar `component-reload`;
o módulo não executa essa troca. Não suportam `immediate`/`next-operation`.
Depois de reconstruir/reiniciar, o host abre o editor com o novo Config ativo
e verifica a revisão aplicada. Salvar nunca marca uma configuração nova como
aplicada ao serviço antigo.

## Migração e fronteiras

Procedimento e inventário, inclusive ausência de configuração e setup no CA:
[migração e bootstrap](configuration-migration.md).

Para mover um JSON legado para config/: conservar backup operacional, ajustar
caminhos relativos para os mesmos destinos, validar, criar seu MD, alterar o
ponteiro/configFile e reconstruir o componente. Só então retirar a fonte antiga
da gestão ativa. A API continua lendo paths legados, mas não os anuncia como
entrada canônica fora de config/. Não há migração automática de credenciais.

Templates/assinaturas mantêm seus paths operacionais anteriores e schema 1.0;
são lidos na próxima renderização. Uma futura migração desses perfis precisa
resolver herança/paths por workspace e criar seus pares MD sem duas fontes.
Esta entrega não os registra como se já estivessem em config/. Journal,
preferências, sessões e auditoria SQLite não são JSONs de configuração.
O CMAIL não possui prompts IA próprios carregados do disco.

CWH/CA controlam instalação, habilitação e autorização por usuário/instância;
CMAIL controla schema, providers, segredos, OAuth e isolamento de mailbox.
Forms e skill do administrador devem usar a mesma API autorizada pelo host.
Nenhum código CWH foi editado nesta entrega e nenhuma instância foi atualizada.

## Validação desta entrega

Na base `5fee2f6` / 26.10.30b, 230 testes passaram no Python canônico com user-site
desativado, incluindo
schemas legados, composição, ausência de efeitos na validação, revisões antigas,
dois editores concorrentes, lock entre processos, falha de substituição,
comparação salva/ativa e rejeição de metadados/caminhos fora do catálogo.
O fragmento real gerado foi validado contra o schema CES compartilhado.
O wheel contém 60 arquivos do módulo, incluindo os dois defaults, conferidos
byte a byte com o fonte. Não inclui ferramentas/testes/staging.

O patch 26.10.30c valida novamente as 36 verificações de lifecycle/configuração/
componentes, incluindo descoberta dos novos exports em um processo Python novo
sem carregar FastAPI. O wheel foi reconstruído e conferido com o fonte do patch.

Não se mediu comportamento em uma instância CWH/CA real nesta rodada.
O aviso de depreciação Starlette/httpx já presente no ambiente continua; nenhuma
dependência global foi alterada. Instalação, ACL, aplicação pelo host e migração
de perfis de aparência permanecem fora dessa evidência.
