# Webmail e composição nos hosts

Desde26.11.2e, a lista pertence ao CMAIL: `mailbox-navigation.mjs` fornece
seleção de pasta, lupa que alterna para busca, novo e-mail, atualizar e linhas
compactas. CAW e CWH usam essa mesma implementação, sem renderizar outra lista.
Data de hoje mostra hora; outros dias mostram somente data. Assunto, remetente
e resumo ficam em linhas únicas com reticências.

O Webmail completo `/` combina lista e conteúdo. `?hosted=1` oculta somente a
marca/configuração local quando o hospedeiro já fornece o topo. O leitor
`?readerOnly=1&folder=...&messageId=...` ocupa todo o espaço restante e conserva
as ações nativas. `?composeOnly=1` entrega composição/prévia nativas; ambas as
apresentações funcionam com autenticação própria ou afirmada pelo host.
Esses parâmetros são apresentação, nunca autenticação ou autorização.

Configurações visíveis: autenticação em `/connection` e template/assinatura.
Tema e dimensões vêm do host de mesma origem; sozinho usa os padrões do módulo.
Nenhuma preferência de layout ou autenticação é inferida a partir de CSS.

Busca envia `q` para a API autenticada da pasta. Gmail/Outlook/IMAP consultam
o provedor; não se limita aos25 e-mails que já estavam na tela. Resultados
nativos são unidos a aproximações de texto/endereços nas até40 prévias recentes
disponíveis, com cache de60s isolado por proprietário, identidade e pasta.
Essa aproximação não é índice fuzzy de toda a caixa. O recorte e a ordem
received-desc são informados no retorno. Corpos e anexos completos não são
baixados em massa para produzir a lista. Não existe polling periódico da caixa.

Busca Gmail usa [messages.list/q](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/list);
Outlook usa [$search nas mensagens](https://learn.microsoft.com/en-us/graph/search-query-parameter).
Ordenação final por recebimento é feita sobre os candidatos devolvidos e o
recorte aproximado; não se afirma exaustividade além dos limites do provedor.

CAW mantém seu proprietário autenticado. No CWH a composição pode afirmar um
único proprietário da empresa para todos os usuários já autorizados no painel.
O módulo continua validando OAuth, CSRF, pasta, ações e claim de envio. Navegação
não envia, arquiva, marca leitura ou exclui automaticamente. Eventos visuais
do leitor usam origem, frame e nonce; envio incerto não deve ser repetido.
