# CMAIL — operação pelo pacote instalado

Distribuição `crania-cmail`, namespace `cmail`, CLI `cmail` ou
`python -s -m cmail`. Oferece Webmail independente e componente ASGI/API para
CAW ou CWH. O host afirma o proprietário; CMAIL mantém conexão, caixa,
provedor, prévias e recibos. Não depende dos fontes do CA.

## Descoberta e instalação

O percurso operacional abaixo é para **cliente sem checkout**: não requer Git,
Node ou build, e não exige ler implementação. Para testar/revisar/implantar em
máquinas distintas, usar o [contrato de validação distribuída](validation/README.md).
O bundle de leitura pública é separado do wheel; testes de engenharia com
inspeção de fontes pertencem ao ambiente validador, não ao cliente de produção.

No Python do consumidor, fora de um checkout:

```powershell
python -s -m pip show crania-cmail
python -s -c "from importlib.metadata import distribution; d=distribution('crania-cmail'); print(*[d.locate_file(f) for f in d.files or [] if str(f).endswith('docs/installed-package.md')], sep='\n')"
python -s -m cmail --help
```

Manuais desta revisão acompanham o wheel em `share/doc/crania-cmail/`.
Instale wheel aprovado e dependências no Python global com
`python -s -m pip install --no-user <wheel>`; confira `python -s -m pip check`.
Isso não configura provedor nem autoriza uma conta.

## Configuração e persistência

Contratos opt-in novos: [contas nomeadas](named-connectors.md), com referência
JSON/MD embarcada, e [anexos de saída](outgoing-attachments.md). Config/CLI1.x
e montagem legada continuam válidas. Não aplicar o schema2 ao host sem sua
adaptação explícita. O CMeio citado operacionalmente é o módulo de e-mail
CMAIL/crania-cmail neste contrato; não corresponde a outro pacote ou transporte.

- Standalone: uma conta por processo/raiz; `.env` contém somente
  `CMAIL_CONFIG_FILE=config/cmail.config.json`. JSONs têm schema fechado.
- Hospedado: o consumidor passa `configFile` diretamente e afirma um
  `Principal` com capacidades explícitas. Não interpretar o `.env` estrutural
  do CA como configuração standalone. API pública em [API](../API.md).
- Caminhos relativos partem da pasta do JSON. Com JSON em `config/`, use
  `state.directory: ../security/cmail`; referências de segredo ficam externas.
- Banco/tokens pertencem à instância e ao owner. DPAPI conserva a identidade
  Windows do serviço; mover arquivo não transfere autorização entre máquinas.
- Novas instâncias usam o assistente `setup` descrito em
  [configuração e migração](configuration-migration.md). Em uma instância
  existente, preserve JSON e estado; não rode setup como tentativa de reparo.

Configuração visível: conexão/autenticação e template/assinatura. Tema e layout
são herdados do hospedeiro. [Estado](state-storage.md),
[configuração pelo host](configuration-host.md) e [aparência](mail-appearance.md).

## Primeira leitura

```powershell
python -s -m cmail check-config
python -s -m cmail status
python -s -m cmail list-folders
python -s -m cmail list-messages --folder INBOX --limit 10
```

Listagem consulta a conta configurada e requer autorização existente. `status`
local não comprova acesso vivo; `status --live` consulta o provedor. `serve`
inicia o Webmail no endereço configurado; não iniciar se o host já o montou.
No CAW a caixa pertence ao workspace autenticado. No CWH, a composição pode
usar uma única caixa da empresa para todos os usuários autorizados, mantendo
os chats do Assistente separados por usuário.

OAuth exige cadastro do aplicativo, callback exato e consentimento da própria
conta. `redirect_uri_mismatch` exige corrigir o registro/URL, não RESET ou cópia
de tokens. Gmail não concede Drive automaticamente. Renovação Microsoft é
opt-in (`microsoft.offlineAccess`); sessão local não prolonga token do provedor.

CAW e CWH adotam a montagem canônica `/cm/cmail`. Para Gmail, o callback é
`<origem>/cm/cmail/auth/google/callback`, independentemente da porta/domínio
do host. A origem completa deve coincidir com o cadastro Google e a configuração
da instância. Prefixos anteriores não devem ser removidos do cadastro de outro
consumidor por efeito de atualizar este pacote.

## Leitura, busca e ações

Webmail completo combina lista e conteúdo. CAW/CWH usam a mesma navegação;
`readerOnly` e `composeOnly` alteram apresentação, nunca autorização.
Pastas, busca, itens compactos e leitor: [layout](webmail-layout.md).
Busca consulta o provedor e combina aproximações nas até 40 prévias recentes;
não é busca fuzzy exaustiva de toda a caixa. Corpos/anexos não são baixados
em massa para montar a lista. Resultados são ordenados por recebimento.

Envio usa preparação e execução separadas:

```powershell
python -s -m cmail send-prepare --input-json mensagem.json
python -s -m cmail send-execute --draft-id <id> --confirmation-token <token> --execute
```

O segundo comando só cabe depois de apresentar e autorizar a prévia exata.
Não registrar o token. Claim é único; falha após iniciar o efeito pode ser
incerta e não deve ser repetida automaticamente. Formato em
[templates e envio](email-templates.md); imagens CID em [imagens](inline-images.md).
Arquivos comuns de envio novo são opcionais pela API, com limites e prévia no
[contrato de anexos](outgoing-attachments.md); CLI/UI não oferecem upload.
Encaminhamento Gmail/IMAP
preserva texto, não anexos. Fora da lixeira, Excluir move; dentro dela,
exclusão definitiva exige confirmação e capacidade do provedor.

## Diagnóstico e limites

Configuração válida, conta autenticada e leitura real são evidências distintas.
Em `401`/concessão inválida, reconectar pelo fluxo nativo; em timeout após
escrita, conciliar recibo antes de qualquer nova ação. Não limpar `security/`
para resolver layout. Atualização preserva estado e exige reiniciar apenas o
consumidor afetado. Documentação de build/testes no README é de manutenção.
Integração CMAIL→AutoLearn/CCI não é entregue por habilitar Webmail.
