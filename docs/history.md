# Histórico

## 2026-10-02 — Extração genérica em e-mail para RPA

Adicionado cmail.extraction: título parcial normalizado, janela em minutos,
interseção com início da operação, REGEX/grupo e remetente opcional. Valor único
em memória, sem log ou marcação de leitura; ambiguidade não reutiliza mensagem
anterior. Polling cancelável a cada 30 segundos, timeout por consumidor.
38 testes CMAIL aprovados, incluindo zero inicial, mensagem antiga/futura,
ambiguidade, grupos e cancelamento. Primeiro consumidor: login MFA Acessórias,
cuja política de portal permanece fora deste módulo.
