# E-mail pelo chatbot

As skills padrão `consultar-email` e `enviar-email` pertencem ao CMAIL.
Leitura, busca e envio não dependem de plugin Gmail do Codex. Configuração,
OAuth, segredos e estado permanecem no backend, em `security/cmail/` da instância.

`CmailApi.search_messages(principal, folder, query, limit=25)` expõe a busca
nativa já usada no Webmail. O resultado conserva metadados de cobertura e
aproximação; não representa uma varredura de todas as pastas.

O descritor CM oferece `manage-messages`, opt-in por consumidor. O CAW pode
expor `actions`, `prepare_manage` e `execute_manage` com `mail.read` e
`mail.manage`. A prévia unitária fixa conta, pasta, mensagem, ação e destino;
a confirmação pertence a novo evento humano do host, nunca ao corpo de e-mail.
Não se oferece exclusão definitiva nessa ponte. A API mantém a operação
irreversível separada para hosts que a autorizem explicitamente.

Ações reais dependem do provedor e dos escopos concedidos. Um host sem a
operação selecionada não recebe a ferramenta; instalar o pacote não concede
acesso. Monitores e plugins administrativos não substituem a identidade do host.

Cadastro de clientes, aliases, marca e relação conta/template pertencem ao
agente. O módulo não embute regras pessoais. Resumo é produzido pelo agente
sobre mensagens realmente lidas, com indicação de conta, pasta e cobertura.
