# Histórico

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
