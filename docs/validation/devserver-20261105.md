# Validação CMAIL — devServer, 05/11/2026

## Escopo e autoridade

Fábio autorizou integração e testes entre suas três contas, com templates,
imagem inline e anexos sintéticos. Nenhum documento fiscal real ou destinatário
de cliente integra o teste. Identificador: `CMAIL-20261105-FD-01`.
Evidências privadas e recibos de execução ficam no agente, fora do Git.

## Base sincronizada e implementação

CMAIL70447dc, CCIbbc2fe2, CA07839cf; Python global3.12 com user-site desativado.
Base CMAIL26.11.5:369 testes simulados aprovados,15 desmarcados.
CCI:25 testes de entrada de e-mail e12 de portal/integração aprovados.
O registro de contas é uma API opcional; CAW permanece no Gmail/config1.x.
Dorotech recebeu JSON nativo separado, reutilizando somente a referência
privada de senha e estado `security/cmail/accounts/dorotech-imap`.

## Execução real em andamento

Quatro envios aceitos uma única vez: Gmail→IMAP/Outlook e IMAP→Gmail/Outlook.
Gmail↔IMAP recebido, com template, PNG inline, PDF e XML sintéticos.
Na base26.11.5, o download Gmail falhou por attachmentId instável; IMAP
listava os arquivos, mas não implementava download. Corrigidos em26.11.5b,
com regressões simuladas; aceite da candidata instalada será registrado aqui.
O leitor público devolve corpo textual; isso não prova ausência de HTML na
mensagem transmitida. Renderização visual exige validação separada no browser.

Outlook/Graph está sendo validado no host dono pela frente LIA .154 Suporte.
Não copiar seu cache OAuth para outra máquina. O Edge externo autenticado
não apareceu no inventário de controle desta sessão; UI ainda não validada.

## Incidente de reinício e recuperação

Ao reiniciar CA, o CCI falhou tanto na versão nova quanto na anterior. Havia
ACL sem escrita para a identidade do serviço nos arquivos SQLite e auxiliares.
Correção limitada aos arquivos necessários, com banco/ACL preservados.
Em seguida, o contrato de identidade exigiu conciliação oficial de estado:
193 ações, zero conflitos bloqueantes com resolve-derived e backup consistente.
Dois componentes ambíguos da origem permaneceram isolados. CA/CCI voltaram
a responder e CWH-5884 iniciou; esse incidente não foi causado pelo OAuth.
Procedimento não deve ser repetido em outras máquinas sem diagnóstico próprio.

## Limites

Este recibo não declara migração completa de consumidores, três contas locais
Graph/Gmail/IMAP prontas no CAW ou aceite visual. Não repetir envios com resultado
incerto. Instalação, leitura, aceitação e recebimento são evidências distintas.
