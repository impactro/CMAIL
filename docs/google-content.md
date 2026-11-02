# Conteúdo Google pelo CMAIL

## Intenção e responsabilidade

O CMAIL é dono da integração Google reutilizável: autenticação, consentimento,
vínculo do proprietário e operações de conteúdo. O host autentica o usuário e
fornece um Principal; não copia tokens nem implementa outro cliente Google.
Gmail autorizado não implica acesso ao Drive, Docs, Sheets ou Slides.

## Procedimento de implementação e validação

1. Reutilizar GoogleAuthService e o armazenamento protegido existente. Publicar
   os escopos exigidos por capacidade e solicitar consentimento incremental
   apenas por ação explícita, nunca durante uma consulta.
2. Acrescentar API pública de conteúdo com capacidades de leitura e escrita
   distintas, sempre vinculadas ao proprietário da identidade Google.
3. Oferecer busca paginada e metadados do Drive e operações delimitadas de
   conteúdo de Docs, Sheets e Slides. Limitar respostas, páginas e entradas.
4. Alterações exigem prévia vinculada ao proprietário e execução confirmada;
   erros após início da escrita são incertos e não autorizam repetição.
5. Publicar operações e skill no descritor CM. O CA continua adaptador: resolve
   identidade e capacidades, sem reimplementar OAuth nem APIs dos provedores.
6. Testar com respostas HTTP simuladas: isolamento entre proprietários,
   escopos ausentes, paginação, limites, falhas, prévia sem escrita e execução
   única. Executar também as regressões existentes de email.

## Limite de homologação deste ambiente

Não existe caixa de email integrada para homologação real. Testes simulados
comprovam contratos e regressões locais, não conexão Google, consentimento de
uma conta real nem envio/recebimento de email. A instalação deve informar essa
diferença. Não criar credenciais de cliente nem iniciar login automaticamente.

## Fontes oficiais

- [Consentimento incremental](https://developers.google.com/identity/protocols/oauth2/web-server#incrementalAuth)
- [Drive API](https://developers.google.com/workspace/drive/api/reference/rest/v3)
- [Docs API](https://developers.google.com/workspace/docs/api/reference/rest)
- [Sheets API](https://developers.google.com/workspace/sheets/api/reference/rest)
- [Slides API](https://developers.google.com/workspace/slides/api/reference/rest)

Os detalhes do contrato implementado e os resultados dos testes serão
registrados aqui após a validação, sem promover simulação a homologação real.
