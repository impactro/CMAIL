# Histórico

## 2026-10-30 — Resultado correto ao mover mensagens Outlook — 26.10.30d

- Componente `26.10.30d`, distribuição `26.10.30.post3`.
- A movimentação Graph aceita `201 Created`, conforme o contrato Microsoft,
  evitando falso erro depois de mover para Lixeira, Arquivo ou outra pasta.
- Preserva o novo ID da mensagem, erros reais e reconexão em HTTP 401.
- Regressões usam transporte simulado; nenhuma mensagem real é movida ou
  excluída pelos testes. Não adiciona retry de operações com efeito externo.

## 2026-10-30 — Descoberta da configuração pública — 26.10.30c

- Componente `26.10.30c`, distribuição `26.10.30.post2`.
- Inclui CmailConfiguration/ConfigurationConflict em `__all__` e `dir(cmail)`
  antes de seu primeiro acesso, preservando import lazy sem FastAPI.
- Mantém a API administrativa de `5fee2f6`. Catálogo CES com optional/next-operation
  segue compatível: conexão obrigatória e aplicação por reload/restart.

## 2026-10-30 — Contrato administrativo de configuração CES — 26.10.30b

- Componente `26.10.30b`, distribuição `26.10.30.post1`.
- API Python `CmailConfiguration` para leitura, validação pelo mesmo parser,
  criação do par inicial JSON/MD e edição com revisão SHA-256 e lock de arquivo.
- Estado salvo/aplicado/restart compara Config ativo com o candidato, mantendo a
  revisão exata carregada quando disponível. Salvar não aplica automaticamente.
- Fragmento `cmail.settings` compatível com catálogo CES v1, paths relativos a
  `config/`, rejeição de symlinks/escape e documentação de mesmo nome-base.
- Preserva configFile, principalResolver, mailWorkspaceRootResolver, schemas
  1.0–1.3 e caminhos explícitos legados. Sem endpoints administrativos novos,
  mudanças de permissões, OAuth, instalação ou edição de fontes CWH.
- Perfis de assinatura/template mantêm locais anteriores; migração de aparência
  ainda precisa ser explícita, sem cópias concorrentes. Não há prompts IA próprios.

## 2026-10-30 — Refatoração de módulos e recursos — 26.10.30a

- Componente `26.10.30a`, distribuição `26.10.30`. Preserva a correção de
  renovação Microsoft opt-in publicada em `6a2da93`, incluindo seus testes.
- Separa rotas, segurança, OAuth Google, DTOs/transporte Outlook, MIME,
  calendário e lifecycle SQLite; mantém imports e contratos públicos.
- Fecha conexões deterministamente, inicializa schema uma vez por arquivo,
  indexa auditoria por owner e persiste o estado de rascunho expirado.
- Teto de memória/quantidade/TTL por prévia e owner, JSON/HTTP limitado e I/O
  síncrono fora do loop ASGI. Retira o envio direto morto do compositor.
- Listagem IMAP evita mensagens/anexos completos; Gmail pede só metadados
  necessários. Imports Python não carregam a interface web antecipadamente.
- Suítes separadas por responsabilidade e ferramentas locais de inventário e
  benchmark. Medidas e limites em [manutenção](maintenance.md).

## 2026-10-29 — Renovação Microsoft explícita — 26.10.29e

- Componente `26.10.29e`, distribuição `26.10.29.post4`.
- `microsoft.offlineAccess` opcional, booleano e desativado por padrão; nenhum
  consumidor ganha acesso persistente apenas por atualizar o pacote.
- MSAL mantém a renovação no cache DPAPI existente. Nova autorização Microsoft
  é necessária para receber a concessão; políticas do Entra continuam válidas.
- A aquisição silenciosa preserva erros OAuth, distinguindo indisponibilidade
  temporária de necessidade de reconexão. Sem retry de envio ou novo login automático.
- Configuração e reconfiguração conservam o opt-in explícito. Testes cobrem
  default, opt-in, tipos inválidos, renovação simulada e falha transitória.
- Não comprova renovação de conta real nem altera configuração de instâncias.

## 2026-10-29 — Compatibilidade dos templates legados — 26.10.29d

- Componente `26.10.29d`, distribuição `26.10.29.post3`.
- Aceita somente `meta http-equiv="Content-Type"` para importar templates HTML
  antigos. Refresh e outros metadados ativos continuam recusados.
- Regressão sintética específica para o metadado; validação operacional dos
  modelos reais permanece fora do pacote genérico.
- 187 testes aprovados; modelos legados Lakatos/FSND renderizados localmente,
  com duas imagens CID no primeiro, sem envio.

## 2026-10-29 — Assinatura e template independentes — 26.10.29c

- Componente `26.10.29c`, distribuição `26.10.29.post2`.
- Padrão genérico, herança empresa/pessoa, escolhas por tipo de mensagem,
  importação de HTML e imagens, arquivos no workspace e modal com prévia isolada.
- Conteúdo e imagens são congelados na preparação. Respostas e encaminhamentos
  web usam o mesmo journal/token, sem refazer o template na execução.
- Microsoft/Graph informa reconexão quando a autorização é inválida; falhas
  transitórias não revogam conta, mudam escopos nem repetem envio.
- 186 testes aprovados, incluindo importação/visualização desktop e móvel,
  isolamento, herança viva, CID, snapshot e distinção entre falha de autorização
  e indisponibilidade. Somente mensagens/provedores sintéticos, sem envio real.

## 2026-10-29 — Confirmação somente na exclusão definitiva — 26.10.29b

- Componente `26.10.29b`, distribuição `26.10.29.post1`.

- Excluir fora da lixeira move imediatamente, sem modal nem flag de confirmação
  obrigatória na API. `mail.manage`, CSRF, contexto da pasta e auditoria permanecem.
- Dentro da lixeira, Excluir mantém confirmação explícita e aviso de exclusão
  definitiva. Mesmo botão, ícone, cor e operações de API distintas.
- Testes de navegador verificam POST direto para lixeira sem clique adicional
  e cancelamento/confirmação da exclusão definitiva apenas dentro dela.

## 2026-10-29 — Excluir por contexto e APIs distintas — 26.10.29a

- Componente `26.10.29a`, distribuição `26.10.29`; instalação e validação do
  consumidor são registradas separadamente do empacotamento do fonte.

- Botão Excluir mantém ícone/cor: fora da lixeira, move para ela; dentro dela,
  solicita confirmação explícita de exclusão definitiva. API Python e HTTP
  separam `trash_message`/`trash` de `delete_permanently`/`delete-permanently`.
  Serviço verifica contexto, capabilities e confirmação; auditoria é distinta.
- Lixeira não depende do flag genérico de movimentação. CAPABILITY IMAP passa
  a ser consultado após autenticar; o cache anterior ao LOGIN podia ocultar
  incorretamente ações. Expurgo definitivo IMAP é restrito ao UID na lixeira.
- Graph/Gmail conferem a pasta/marcador real antes de excluir definitivamente.
  Gmail respeita o grant já concedido, sem ampliar consentimento automaticamente.
- Regressão também expôs intermitência preexistente de IDs/tokens aleatórios
  iniciados por hífen na CLI. Prefixos fixos nos novos valores opacos evitam
  interpretação como opção; confirmações anteriores continuam válidas.
- 154 testes aprovados, incluindo cinco de navegador e regressões de
  confirmação, CSRF, pasta real, CAPABILITY pós-login e UID isolado.
  Validação somente com contas, provedores e mensagens sintéticas; não equivale
  à homologação de exclusão em uma caixa real.

## 2026-10-28 — Barra contextual e organização do Webmail — 26.10.28a

- Componente `26.10.28a`, distribuição Python `26.10.28`, incluindo as imagens
  CID da evolução anterior. Instalação e homologação de cada consumidor são
  verificações operacionais separadas da publicação do fonte.

- Ações da mensagem selecionada passam ao cabeçalho com ícones SVG locais,
  nomes acessíveis, dicas e navegação anterior/próxima. Pastas recebem ícones
  e nomes de apresentação; filtro atua somente na lista carregada. Leitor
  mostra destinatários e inventário de anexos, sem executar HTML externo.
- Mantidos os IDs funcionais, classes públicas `cm-*`, tokens `--ca-ui-*`,
  ponte de tema e prefixos ASGI. Base independente e host de teste com frame
  verificados em claro/escuro e larguras 1440, 1064, 768 e 390 px.
- Disponibilidade de ações combina provider e capabilities. IMAP passa a
  marcar leitura, mover por UID e responder/encaminhar com pasta explícita.
  Encaminhamento IMAP é textual, sem anexos, com limite informado na confirmação.
  Destinos de arquivo/lixeira são pastas reais; excluir confirma antes de mover.
- Movimentação IMAP usa MOVE ou COPY/STORE/UID EXPUNGE; nunca expurga a caixa
  inteira ou repete automaticamente uma falha. Graph resolve IDs de arquivo
  e lixeira sem depender do idioma. Gmail inclui lixeira e mantém destino e
  origem coerentes ao restaurar; Enviados/Rascunhos não são destinos manuais.
- Regressão: 139 testes sintéticos aprovados, incluindo quatro testes de
  navegador. Conferência visual própria, sem uso de conta real ou envio.

## 2026-10-24 — Imagens CID opcionais, somente fonte

- Payload `inlineImages` liga PNG/JPEG ao HTML por `img src="cid:..."`, com
  oito imagens e dois MiB totais no máximo. Sem caminhos, downloads ou SVG.
- Corpo e bytes ficam no mesmo snapshot/token confirmado; prévia inclui
  metadados e hash. MIME related compartilhado por Gmail/SMTP/IMAP; Graph
  usa imagens inline nativas. Anexos gerais continuam recusados.
- Principal, autenticação, refresh, TLS, configuração, schema do banco e
  tratamento de envio incerto não foram alterados. CLI aceita arquivo JSON
  de imagens somente na preparação, nunca para substituir o rascunho.
- 48 testes focais e 123 completos aprovados, todos sintéticos; sem envio.
  Integração privada do consumidor montou MIME com apresentação e assets
  aprovados, preservando bytes e HTML no roundtrip, sem chamar provider.
- Fonte não instalada nem publicada; metadados da distribuição anterior
  permanecem até a geração deliberada de uma candidata. Não afirmar E2E de
  Gmail, Outlook ou entrega. Contrato: `docs/inline-images.md`.
## 2026-10-21 — Gmail SMTP/XOAUTH2 por arquivo

- `26.10.21a`: schema `1.3` com transporte explícito `api`/`smtp`; schemas
  anteriores preservados. SMTP fixo Google, TLS obrigatório, identidade por
  AUTH, status sem envio e refresh em memória; sem fallback ou senha de app.
- Consentimento SMTP opcional usa grant próprio, PKCE e valida a caixa antes
  de criar arquivo novo. CLI de envio e templates preservam duas fases.
- Journal isolado por conta/transporte, Bcc e recibo DATA; falhas incertas
  não são repetidas. SMTP não anuncia leitura, pastas ou webmail.
- Validação: 100 testes sintéticos de regressão/fonte aprovados; 19 testes
  SMTP também aprovados a partir do diretório externo ao checkout. A validação
  de conta e a implantação reais são registradas privadamente no host consumidor.

## 2026-10-19 — Gmail Por Arquivo E Envio Em Duas Fases

- Candidata `26.10.19a`, distribuição `26.10.19`: modo headless `gmail-file`
  no schema `1.2`, preservando os schemas/modos anteriores. Referência externa
  authorized_user, refresh em memória e identidade real conferida no Gmail.
- CLI `cmail.gmail_file auth/init/status/refresh`: consentimento Google Desktop
  explícito, URL, loopback efêmero, state/PKCE e arquivo novo; uso normal nunca
  abre login. Endpoints fixos, sem redirects, sem SSO CA e sem owner arbitrário.
- `cmail.enviar --gmail`: corpo/arquivo UTF-8, HTML ou template estrito,
  preparação por padrão e execução exclusiva de draft confirmado. Renderer
  público exportado, com escape padrão e campos HTML explícitos.
- Prévia inclui o snapshot exato normalizado do journal; execução não relê o
  template e não faz replay após claim incerto. Anexos continuam recusados.
- Suíte completa: 81 testes aprovados, somente fixtures/provedores simulados,
  incluindo regressão web existente. AST/UTF-8/JSON/diff conferidos. Sem leitura
  de token real, consentimento real, envio, instalação, reinício, commit ou push.
- Namespace editorial `knowbase/mail/templates/` documentado no CA, sem dados
  pessoais no template genérico. Integração opcional CVai é entrega de outro dono.
- Smoke real relatado pelo consumidor: refresh aceito, porém a Gmail API do
  projeto legado retornou `403 SERVICE_DISABLED`. Não declarar essa conta
  operacional na rota API. SMTP XOAUTH2 é extensão pendente de autorização
  específica, sem campo `transport` nem fallback implementado nesta candidata.

## 2026-10-02 — Extração genérica em e-mail para RPA

Adicionado cmail.extraction: título parcial normalizado, janela em minutos,
interseção com início da operação, REGEX/grupo e remetente opcional. Valor único
em memória, sem log ou marcação de leitura; ambiguidade não reutiliza mensagem
anterior. Polling cancelável a cada 30 segundos, timeout por consumidor.
38 testes CMAIL aprovados, incluindo zero inicial, mensagem antiga/futura,
ambiguidade, grupos e cancelamento. Primeiro consumidor: login MFA Acessórias,
cuja política de portal permanece fora deste módulo.

## 2026-10-14 — Apresentação WebMail compatível com temas CA

Versão26.10.14a, distribuição26.10.14. Classes `cm-*`, tokens públicos
e ponte de mesma origem, fallback neutro e foco/contrastes revisados nos
quatro temas. Regiões, IDs, ações e autenticação preservados. 44 testes
focais aprovados e revisão visual no Edge com dados fictícios. Sem envio
ou consulta adicional às contas reais.

- Contraprova real26.10.14b/post1: itens de mensagem preservam fundo neutro
  e datas legíveis; não herdam preenchimento de botão de ação. Apenas
  apresentação, sem abrir, marcar, arquivar ou enviar mensagens.

## 2026-10-30 — Orientações genéricas por capacidade

- Versão: `26.10.30e`; pacote `26.10.30.post4`.
- Resultado: Orientação distingue capacidades reutilizáveis de identidade/finalidade do consumidor e conta autenticada; preserva escopo e controle de envio.
- Validação DEV: 238 passed, 1 warning in 34.19s. Revisão de diff e dos descritores de skills; nenhuma mudança de operação, schema, conta ou permissão.
- Entrega: fonte publicada e pacote instalado no Python global do UniServer, com 60 arquivos conferidos byte a byte contra o wheel do commit `8396eb8`. Rollback preservado; CA saudável e CWH conectado. Sem geração de mídia, acesso a caixa real ou publicação de site nesta validação.
