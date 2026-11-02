# Navegação de leitura no hospedeiro

O CAW oferece um piloto sobre as APIs CMAIL existentes: `GET /api/folders`,
`GET /api/messages` e `GET /api/messages/{identifier}`. A sessão e a resolução
da conta continuam no CMAIL; o menu não fornece principal, token ou caminho
de armazenamento. Gmail e Outlook usam o mesmo DTO público normalizado.

O hospedeiro troca a lista de conversas pela lista de e-mails e conserva as
pastas em seletor superior. Isso também permite sair de um CWH hospedado para
o e-mail sem transferir a conta nem parar o transporte. Lista e leitura possuem
cancelamento/descarte de resposta antiga por pasta e workspace, loading e
erro/retry próprios. O corpo usa texto normalizado, sem interpretar conteúdo
recebido como HTML confiável. O Webmail completo permanece disponível.

O piloto pede até 25 mensagens recentes por pasta; os endpoints atuais de
lista não oferecem cursor para percorrer toda a caixa. Não declarar paginação
completa ou caixa vazia quando houver falha de autorização. O piloto não
chama endpoints de escrita: abrir mensagem não a marca como lida, nem envia,
move ou apaga. Consentimento adicional, publicação e envio não são parte do
teste de leitura.

Validação sintética do host deve incluir troca de pasta durante leitura,
troca de identidade, erro/retry e volta ao chat. OAuth/provedor real devem
ser validados no navegador externo já autenticado da instância autorizada;
recebimento de JSON e health isolados não encerram aceite visual.
