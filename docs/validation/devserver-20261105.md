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

## Resultado das APIs

Seis envios aceitos uma única vez e seis recebimentos confirmados. Contas
Gmail/IMAP no devServer; Graph no host LIA, pelo grant existente.

| Origem | Destino | Aceitação | Recebimento | PDF/XML/PNG |
| --- | --- | --- | --- | --- |
| Gmail | IMAP | Sim | Confirmado | 3 hashes iguais |
| Gmail | Outlook | Sim | Confirmado pela LIA | 3 hashes iguais |
| IMAP | Gmail | Sim | Confirmado | 3 hashes iguais |
| IMAP | Outlook | Sim | Confirmado pela LIA | 3 hashes iguais |
| Outlook | Gmail | Sim | Confirmado | 3 hashes iguais |
| Outlook | IMAP | Sim | Confirmado após atraso de entrega | 3 hashes iguais |

Nenhum envio repetido. Dezoito arquivos recebidos conferidos; HTML/CID confirmados
no MIME de Gmail↔IMAP e Outlook→Gmail/IMAP, com um inline e dois anexos comuns
por mensagem. Acentuação preservada. O retorno Outlook→IMAP demorou a aparecer:
foi conciliado no mesmo run, sem interpretar atraso como autorização para retry.
Na base26.11.5, o download Gmail falhou por attachmentId instável; IMAP
listava os arquivos, mas não implementava download. Corrigidos em26.11.5b,
com regressões simuladas. Candidata 26.11.5.post1 instalada: 371 testes simulados
aprovados/15 desmarcados, pip check íntegro e 80 arquivos iguais ao wheel.
SHA256: `0f95918a48c0779d8df047e56d84c32d307d0dea3a7795181f3d9a9f7fb84699`.
Nos mesmos e-mails iniciais, os seis downloads (PDF/XML/PNG nos dois sentidos) passaram
com hashes idênticos. Inspeção MIME confirmou HTML, referência CID, uma imagem
inline e dois arquivos comuns em cada mensagem. Não houve reenvio.
Bundle portátil executado fora do checkout, usando pacote instalado:
dois probes reais aprovados, Gmail e IMAP, sem envio pelo bundle.
O leitor público devolve corpo textual; isso não prova ausência de HTML na
mensagem transmitida. Renderização visual exige validação separada no browser.

Outlook/Graph foi validado no host dono pela frente LIA .154 Suporte.
O vínculo foi confirmado vivo e os dois canários chegaram à INBOX. A leitura
de anexos encontrou HTTP400 por contentId no $select da coleção base Graph.
Correção publicada em73155e6, versão26.11.5c/post2:372 simulados aprovados.
Wheel: `5e83280755b06f5b10e852c71f3a2dacb7d1a8b95682ad737e8494e9decf4e46`.
Download individual continua fornecendo CID; não houve alteração de OAuth.
Na LIA, o patch resolveu a leitura dos seis arquivos recebidos. Os dois envios
de retorno tiveram accepted=true e uma execução por destino. Localmente, post2
também foi instalado:80 arquivos iguais ao wheel, pip check e health positivos.
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
Graph/Gmail/IMAP prontas no CAW ou aceite visual. O adaptador pessoal legado
`mail_agent.py` ainda bloqueia anexos CMAIL e conserva rotas SMTP próprias;
sua convergência não foi executada nesta validação do módulo. Os canários
usaram exclusivamente a API nativa CMAIL. Não repetir envios com resultado
incerto. Instalação, leitura, aceitação e recebimento são evidências distintas.

## Publicação e recuperação

- CMAIL: e31433a (Gmail/IMAP) e73155e6 (Graph), publicados em main.
- CServer: fba61b2 registra a operação local; recibo do FormServer pertence à LIA.
- Serviços locais recuperados: CA/CCI/AI Host saudáveis, três CWH conectados.
- ZIP incompleto da primeira tentativa e prévias consumidas dos quatro envios
  locais removidos. Backups válidos, recibos e journal nativo preservados.
