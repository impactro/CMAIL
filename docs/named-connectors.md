# Contas nomeadas — primeira etapa implementada

API Python opcional para composição por hosts confiáveis. `CmailApi`,
`Config`, CLI, Webmail e callbacks existentes permanecem com seus contratos
1.x. Nenhum consumidor é migrado automaticamente; não substituir seu JSON
ativo pelo schema2 antes da adaptação do host. Não há endpoint novo.

## Registro e configuração

`ConnectorConfig.from_file(path, root=raiz_da_instancia)` lê um único JSON;
`ConnectorConfig.load(root)` usa o mesmo ponteiro `CMAIL_CONFIG_FILE` do `.env`.
Não há cascata nem busca por outros arquivos de configuração.

O contrato2.0 contém exatamente:

| Campo | Tipo e significado |
| --- | --- |
| schemaVersion | String `2.0`. |
| webmailConnectorId | ID existente; seleção fixa declarada para futura composição do Webmail. |
| connectors | Objeto não vazio; chaves são IDs estáveis, valores são configurações nativas completas1.0–1.3. |

IDs usam letra minúscula inicial, letras/números ASCII, `_` ou `-`, até64
caracteres. Cada `state.directory` deve resolver para
`<root>/security/cmail/accounts/<connectorId>`. Caminhos nos documentos filhos
são relativos ao JSON principal, conforme o parser nativo. Root é fornecido
pelo host, não por parâmetros de uma requisição. Estado compartilhado,
sobreposto ou fora desse diretório é rejeitado. Segredos permanecem referências.
Validar documento não cria arquivos, serviços ou conexões.

Dois conectores podem usar Gmail ou Microsoft. Endereço esperado repetido no
mesmo modo é rejeitado: aliases da mesma caixa ainda exigem contrato específico.
Quando o provedor não declara endereço esperado, essa detecção estática não
comprova que duas autorizações futuras pertençam a caixas distintas.
`setup` e novos conectores `gmail-file` estão fora desta etapa; não se removeu
a restrição do operador local para transformá-los em contas de host.

## API pública

```python
from cmail import ConnectorConfig, ConnectorRegistry

config = ConnectorConfig.from_file(config_path, root=instance_root)
registry = ConnectorRegistry(config)
# A identidade owner vem da autenticação/contrato EXISTENTES do host.
principal = registry.principal_for_owner(
    'personal', authenticated_owner, frozenset({'mail.read'}))
mailbox = registry.bind('personal', principal)
folders = mailbox.folders()
```

`principal_for_owner` é composição confiável, delegada ao resolvedor nativo;
nunca expor owner livre a modelo/HTTP. Não cria grants nem amplia capacidades.
`bind(connector_id, principal)` exige conector explícito e principal de e-mail
nativo da conta; revalida o vínculo a cada chamada. Revogação/rebind falha antes
da operação. Não há conta escolhida por ordem, alias, nome ou fallback.

O objeto vinculado oferece `folders`, `messages(folder, limit)`,
`message(folder, id)`, `attachments(id)`, `attachment(id, attachment_id)`,
`annotation_reader()`, `prepare_send(payload)` e
`execute_send(draft_id, confirmation_token)`, delegando ao CMAIL existente.
O reader exige `mail.read`; preparar/enviar preserva as verificações nativas.
Preparação identifica `connectorId`; confirmar exige o mesmo objeto/conta.
Prévia de outra conta/owner não pode ser executada, nem autoriza retry.
Não foi adicionado envio de anexos comuns.

`list_connectors({id: principal_nativo})` lista somente os conectores que o
host já autorizou e forneceu, com ID/provedor/capacidades/seleção fixa, sem
endereços, caminhos ou tokens. Vínculo inválido falha explicitamente.

`native_api(connector_id)` entrega a API nativa para composição confiável de
Webmail/contratos ainda não cobertos pela fachada; conservar no backend.
Serviço é criado sob demanda, uma vez por conector, com exclusão mútua.
Não inicia thread, listener ou consentimento. Não há descoberta automática
de contas, administração de OAuth ou roteamento de callbacks neste registro.

## Compatibilidade sem migração

```python
registry = ConnectorRegistry.from_legacy(existing_cmail_api, connector_id='current')
assert registry.native_api('current') is existing_cmail_api
```

Esse caminho reutiliza exatamente o serviço já montado, seu estado, owner e
grants. Preserva também os contratos do operador local na API nativa. Nenhum
arquivo é copiado/renomeado, nenhum token é regravado e nenhum novo serviço
é construído. O JSON1.x existente não muda. Não converter para o registro2.0
como efeito de um SYNC. Retorno: continuar usando a API e o JSON anteriores;
não apagar estados de contas criadas em testes/migrações posteriores.

## Limites e próximos contratos

Esta etapa não adapta CA/CX/CWH/CCI/CVAI, não adiciona seletor visual nem muda
permissões, ACL, OAuth ou sessão. O host continua responsável pela autoridade
de cada usuário sobre conectores IMAP/contas corporativas compartilhadas.
Receber um ID/owner por si só não autentica o chamador.

Próximas etapas: edição administrativa versionada do registro; onboarding e
callback por conector; aliases/deduplicação de caixas; conta de serviço
gmail-file; anexos comuns; consumidores e migração testada. O documento de
[proposta](named-connectors-proposal.md) preserva o escopo completo futuro.
