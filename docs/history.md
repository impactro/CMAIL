# Histórico

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
