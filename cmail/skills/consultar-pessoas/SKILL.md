---
name: consultar-pessoas
description: Localizar contatos pessoais, funcionários ou endereço de e-mail corporativo no diretório Microsoft da conta autenticada.
---

# Consultar Pessoas

Use quando a pessoa pedir um contato salvo, endereço corporativo, funcionário,
cargo ou identificação de alguém na empresa. Esta skill é de leitura e usa a
API pública do CMAIL com `Principal` previamente validado pelo host e a
capacidade `mail.read`.

1. Para um contato pessoal, consulte `contacts`.
2. Para funcionário ou endereço corporativo, consulte `directory` pelo nome ou
   e-mail; a busca é limitada a 50 resultados e retorna somente identidade
   básica.
3. Para localizar mensagens de alguém, use a skill de caixa de e-mail antes de
   tentar resolver a pessoa no diretório.
4. Não misture contas, não aceite `workspaceId` do prompt e não exponha IDs ou
   dados além do necessário.

O diretório é uma leitura corporativa disponível somente para contas Microsoft
organizacionais já autorizadas. Gmail e IMAP não simulam essa capacidade.
