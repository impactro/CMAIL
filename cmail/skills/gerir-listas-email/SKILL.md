---
name: gerir-listas-email
description: Consultar ou manter listas locais de destinatários no CMAIL.
---

# Gerir Listas De E-mail

Esta skill é consumida por runtimes agentes. Eles devem chamar `CmailApi` com
um `Principal` validado e a capacidade `lists.manage`; cookie/token web não é
aceito. Listas pertencem à identidade no SQLite próprio do CMAIL e contêm dados pessoais. Antes de
criar ou substituir uma lista, confirme nome, finalidade e destinatários. Não
importe contatos de outra conta ou workspace por proximidade de nome.

O comando `lists` sem arquivo apenas consulta no modo operador local. Com `--input-json`, valida todos
os endereços e substitui atomicamente os membros da lista homônima.
