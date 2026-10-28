# Histórico

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
