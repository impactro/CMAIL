---
name: gerir-listas-email
description: Consultar ou manter listas locais de destinatários no CMAIL.
---

# Gerir Listas De E-mail

Listas pertencem ao SQLite próprio do CMAIL e contêm dados pessoais. Antes de
criar ou substituir uma lista, confirme nome, finalidade e destinatários. Não
importe contatos de outra conta ou workspace por proximidade de nome.

O comando `lists` sem arquivo apenas consulta. Com `--input-json`, valida todos
os endereços e substitui atomicamente os membros da lista homônima.
