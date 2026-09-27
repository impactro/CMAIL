---
name: consultar-email
description: Consultar configuração, pastas, mensagens e anexos da caixa autenticada por meio do componente CMAIL.
---

# Consultar E-mail

Esta skill serve a runtimes agentes que incorporam o CMAIL, incluindo CA e CAX
mínimos; não é instrução da interface humana standalone. Pela API Python, passe
sempre um `Principal` cuja assertion já tenha sido validada pelo host e exija
`mail.read`. Cookie ou token da interface web não é assertion de agente.

Use `check-config` para validação offline e `status --live` somente quando uma
conexão real for necessária. `folders`, `messages` e `message` são leituras do
provedor configurado. Declare conta autenticada, pasta, limite e momento da
consulta. Para marcar leitura ou mover/limpar mensagens, exija também
`mail.manage` e confirme a pasta de destino; não faça exclusão permanente.

Para mensagens de uma pessoa pelo nome, pesquise primeiro a caixa de e-mail.
Só use a skill de pessoas quando for preciso descobrir o endereço corporativo
ou identificar um funcionário; contatos pessoais e diretório corporativo são
fontes diferentes.

Resultado vazio vale apenas para a pasta e o limite testados. Não exponha senha,
arquivo de segredo, corpo de terceiros ou identificadores internos além do
necessário. A interface individual é iniciada por `serve` e permanece local.
O CAX chama os métodos de `CmailApi`; não importa `ca.*` nem lê o SQLite.
