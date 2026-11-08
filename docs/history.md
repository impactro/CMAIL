## 26.11.8a — Templates de distribuição no Windows

Guard comum do CUI identifica templates por caminho/recibo normalizados,
negando variantes de prefixo/extensão sem distinção de caixa. HTML público,
aliases, cache e montagem nomeada permanecem válidos. Correção de
CUI:BUG-CUI-STATIC-TEMPLATE-CASE-20261108 adotada e testada, sem alteração de
provedores, OAuth, CSRF, prévias, envio ou dados de caixa.

## 2026-11-08 — Revisão independente da apresentação CUI

Revisão ASTRA em cc578b5 não confirmou defeito funcional material na migração;
sete testes Node e quatro Python focais passaram,34 recursos foram conferidos
por hash e a estrutura funcional dos nove templates foi preservada. Identificada
exposição do template Jinja bruto por variantes de maiúsculas no Windows,
sem dados de conta renderizados. A fonte do adaptador é tools/runtime_assets.py
do CUI: achado consolidado no dono como BUG-CUI-STATIC-TEMPLATE-CASE-20261108,
sem manter outra cópia da tarefa no consumidor. O registro transitório anterior
BUG-CMAIL-CUI-STATIC-CASE-20261108 foi conciliado para essa referência.
Aceite limitado a fonte/fixtures, sem provedor real, envio ou caixa ativa.
Esta revisão não alterou produto ou runtime.

## 26.11.7a — apresentação CUI

Templates Jinja e estilos passam ao CUI; lista de e-mails usa o renderizador
comum com callbacks do CMAIL. Snapshot completo distribuído no wheel,
autoescape preservado e recarga de template tolerante à troca de release.
Somente assets públicos com hash recebem cache imutável; páginas e APIs
continuam privadas. OAuth, owner, CSRF, prévias, confirmação e isolamento
de conteúdo permanecem sob responsabilidade do CMAIL. Guia: [CUI](CUI.md).

Validação: suíte sintética Python, treze testes Node, cinco testes focais de
distribuição/layout e matriz de sete temas no Browser. Nenhum envio real.

## Verificação de regressão — 07/11/2026

O teste responsivo compara dimensões no mesmo viewport do elemento, inclusive
em iframe. A fixture do provedor declara busca nativa na pasta, conforme o
contrato usado pela navegação. Corrige falsos erros de homologação; não altera
CSS, autenticação, transporte, caixas reais ou envio. Entrega apenas de testes
e documentação, sem nova versão ou reinstalação do runtime.

## 26.11.6b — Aprovação sem vencimento por relógio

Rascunhos de envio deixam de vencer após dez minutos. O host consumidor valida
a continuidade da conversa e a aprovação da prévia pendente; a passagem de
horas/dias não a invalida. Claim continua unitário, por proprietário e snapshot,
sem reativar rascunhos consumidos ou incertos. Sessões OAuth/web mantêm seus
próprios prazos técnicos, independentes da decisão humana.

## 26.11.6a — Busca acentuada no Microsoft IMAP

Exchange pode retornar BAD antes de BADCHARSET para bytes acentuados em
quoted-string. O modo Microsoft IMAP usa diretamente a cobertura parcial
explícita para consulta não ASCII, preservando o termo e evitando o comando
inválido. Busca ASCII continua nativa. Sem alteração de mensagens.

## 26.11.6 — Busca IMAP compatível com Exchange

Diagnóstico vivo encontrou BADCHARSET US-ASCII no Microsoft IMAP local.
Busca ASCII passou sem charset explícito; remetente também entra na consulta.
Recusa de charset em texto acentuado gera cobertura parcial explícita de
resumos recentes; outros erros não são ocultados. Nenhuma mensagem alterada.

## 26.11.5g — Contrato de e-mail para chatbot

Skills padrão ampliadas para busca, leitura, resumo, organização e templates
do consumidor. API pública expõe a busca existente; descritor adiciona gestão
opt-in. Marcação de leitura Microsoft IMAP conserva a pasta selecionada.
Validação somente sintética para alterações; nenhuma mensagem real apagada.

## 05/11/2026 — preservação de leitura e atualizações

Fonte 26.11.5f / Python post5. Leitor conserva o conteúdo anterior enquanto busca a próxima mensagem, desabilita ações da seleção pendente e cancela buscas substituídas. Respostas antigas não sobrescrevem a leitura atual. Erro restaura a seleção anterior; consultas auxiliares de listas só começam após abrir a mensagem e não bloqueiam sua leitura.

Conferência própria: 6 frontend e 401 Python aprovados. Cenários sintéticos, sem envio ou
conta real de cliente. O caso do cliente sem instância identificada não teve
causa individual certificada. Implantação consolidada aguarda janela OPS/ALP;
esta publicação não altera runtime ou credenciais.


## 26.11.5e — Microsoft IMAP/SMTP OAuth como alternativa ao Graph

Novo modo microsoft-imap com cliente público MSAL, XOAUTH2 e cache DPAPI;
migração explícita de OMAIL, código de dispositivo e renovação silenciosa.
Destinos TLS, conta, aplicativo e tenant validados. Reutiliza o provedor MIME,
prévia, anexos, templates, Cc/Bcc e journal; sem senha, Graph ou fallback.
401 testes sem navegador passaram; suite integral anterior teve uma falha
visual já registrada. No DEV-FSND, cache antigo retornou AADSTS50173; login
renovado no Edge, AUTH IMAP/SMTP e leitura de pastas/um item aprovados, sem envio.

## 2026-11-05 — aceite Cc/Bcc no DEV-FSND

CMAIL26.11.5d/post3 e CA26.11.5e/post5 instalados:47 testes focais CMAIL,
116 CA e24 do adaptador pessoal passaram. Edge autenticado exibiu os três
grupos nas prévias oficiais Gmail/IMAP e na confirmação Webmail, cancelada.
Zero send-execute; preservados contas, autorizações,158 configurações e12
schemas de bancos. Outlook local segue desabilitado. Evidência em
[validação do consumidor](validation/devserver-20261105.md).

## 26.11.5d — Cc e Bcc em novas mensagens

API, CLI e Webmail preservam os grupos na prévia confirmada e os encaminham
para Gmail API, SMTP/XOAUTH2, IMAP/SMTP e Microsoft Graph. SMTP conserva Bcc
fora dos bytes transmitidos; chamadas legadas conservam a proteção anterior
de listas. Respostas/encaminhamentos recusam cópias adicionais explicitamente.
Normalização pública compartilhada com o consumidor CAW, sem transporte novo,
alteração de credenciais ou envio real. Ver docs/cc-bcc.md e testes focais.

## 2026-11-05 — aceite das contas pessoais no CAW

Consumidor CA26.11.5d/CAIXQ26.11.5 instalado e testado no Edge: Gmail padrão e
IMAP Dorotech com leitura nativa e prévia por conta/template/anexo. OAuth e
bytes/journal permanecem no CMAIL26.11.5c;0 envios nesta etapa. Outlook local
desabilitado por Fábio, sem reativação automática pendente. Ver
[evidências e limites](validation/devserver-20261105.md). Não implica aceite de
outros hosts, seletor visual ou migração para o registro2.0.

## 26.11.5c — consulta de anexos Microsoft Graph

Validação na LIA encontrou HTTP400 ao selecionar contentId na coleção base
de attachments. A listagem usa somente campos do tipo base; o download do
arquivo devolve contentId/isInline quando disponíveis. Nenhuma mudança de
OAuth ou reenvio. Regressão reproduz a restrição da consulta OData.
Contrato oficial: [attachment](https://learn.microsoft.com/en-us/graph/api/resources/attachment?view=graph-rest-1.0)
e [fileAttachment](https://learn.microsoft.com/en-us/graph/api/resources/fileattachment?view=graph-rest-1.0).

Validação:372 testes simulados aprovados;2 probes reais portáteis Gmail/IMAP
aprovados fora do checkout. Instalação e health confirmados no devServer;
LIA confirmou instalação e regressões Graph. Seis canários aceitos, seis
recebimentos/dezoito hashes confirmados. Nenhum cliente real,
documento fiscal real ou reenvio. Aceites restantes ficam na fila; evidência
completa em [validation/devserver-20261105.md](validation/devserver-20261105.md).

## 26.11.5b — leitura real de anexos Gmail e IMAP

Validação entre contas autorizadas encontrou identificadores de download Gmail
variando a cada GET da mesma mensagem. Descritores agora expõem a parte MIME
estável e o download resolve o identificador atual, verificando pertencimento.
IMAP passa a fornecer IDs/download para anexos comuns e inline na INBOX, com
limite de25MiB. Leitura completa usa BODY.PEEK[], preservando flags.

Nenhum transporte de envio novo, token copiado ou alteração de interface.
Regressões simulam rotação de identificador e MIME aninhado. Evidência por
ambiente e limites em [validation/devserver-20261105.md](validation/devserver-20261105.md).

## 26.11.5a — testes por provedor e validação distribuída

Testes separados fisicamente em IMAP/SMTP, Gmail API/OAuth web, Gmail
API/OAuth por arquivo, Gmail SMTP/XOAUTH2 e Outlook/Graph. Contratos
compartilhados continuam explícitos; markers distinguem simulado, browser e
live. Comparação da coleta preservou os 382 casos anteriores sem perda ou
duplicação por nome/parametrização. Incluídos teste da chave física e probe live.

369 testes sintéticos aprovados, 15 desmarcados (browser e probe live).
Probe real fica pulado por padrão; opt-in sem plano é recusado na coleta.
Bundle com manifesto SHA256 validado fora do checkout: zero implementação,
skip sem conexão. Não foram usados Gmail real, Outlook, IMAP, consentimento,
envio ou contas locais; homologação por perfil segue para a máquina dona.

AnnotationReader expõe mailbox_id opcional pelo subject nativo verificado,
mantendo account_id e checkpoints anteriores. CCI pode rejeitar aliases entre
Stores sem presumir identidade pelo endereço. Não muda grants/autenticação.

Documentação embarcada inclui plano JSON/MD, roteiro de homologação, limites
por transporte, recibo sanitizado e descoberta via metadata. Cliente somente
pacote, engenharia, homologação e OPS têm percursos próprios; referências de
manutenção ao CServer não exigem checkout no cliente. Wheels são candidatas
DEV, sem instalação/reinício. Contrato: [validation/README](validation/README.md).

## 26.11.4b — anexos comuns no envio novo

Prévia nativa aceita arquivos fornecidos pelo host, normaliza/congela bytes,
expõe manifesto de metadados/SHA256 e verifica integridade e vínculo de conta
antes do claim. Arquivos comuns e inline são distintos em MIME/Graph.
Gmail API, Gmail SMTP/XOAUTH2, IMAP/SMTP e Graph suportam a opção aditiva;
provedor sem capacidade declarada é recusado antes de preparar.

Até8 arquivos e2MiB somados com inline; snapshot limitado a3MiB. Sem leitura
de paths/URLs, novos grants ou upload sessions. Novo status de draft impede
execução por versões antigas que descartariam anexos. Falha após início segue
incerta, sem repetição. Resposta/forward com arquivos são recusados.

367regressões aprovadas/4puladas fora das2suíteslayout; conferência posterior
71focais aprovada com proteção de rollback. Testes exclusivamente sintéticos,
sem envio, OAuth, migração de host ou instalação real. Limites e contrato em
[outgoing-attachments.md](outgoing-attachments.md).

## 26.11.4a — registro opcional de contas nomeadas

Primeira etapa autorizada: ConnectorConfig2.0 reutiliza configurações nativas
por conector e valida estado separado. ConnectorRegistry cria serviços sob
demanda, exige seleção explícita, conserva o resolvedor nativo de owner e
permite reaproveitar exatamente a API/serviço legados sem mover arquivos.
Webmail, callbacks, permissões e consumidores permanecem inalterados.

348testes de regressão aprovados/4pulados, excluindo as duas suítes de layout
Playwright; conferência final41focais aprovada, incluindo registro, OAuth
sintético, revogação, contas/owners cruzados, prévias e configuração exemplar.
Nenhuma conta, sessão, token, envio ou instalação real participou dos testes.
Contrato, configuração e limites em [named-connectors.md](named-connectors.md).

## 04/11/2026 — Revalidação do SYNC Full no LAB

Fetch e revisão confirmaram main alinhada, sem alterações locais pendentes.
Desde a fonte instalada2de2ec0 (26.11.3.post2), os commits seguintes são
documentais: proposta de contas nomeadas e conciliação da fila compartilhada.
Nenhum delta em cmail/ ou nos requisitos; pacote e serviços preservados,
sem reinstalação ou reinício.19testes focais aprovados e pip check limpo.
Contas nomeadas continuam proposta; aceite de leitura/importação real e
pendência de viewport não foram executados nem encerrados por este SYNC.

## 04/11/2026 — análise de contas nomeadas

[Proposta arquitetural](named-connectors-proposal.md) distingue o contrato
atual da evolução: registro de conectores, isolamento por owner, anexos,
templates e convergência de CA/CX/CWH/CCI/CVAI. Webmail permanece fixo;
desenvolvimento e seletor visual não foram implementados. Fontes relacionadas
sincronizadas e pacotes locais comparados; diagnóstico final da LIA .154
acompanha o chat responsável por sua implantação.

A análise concluída saiu da fila. A evolução ficou em SUGESTÃO para revisão,
e `.agents/tasks.md` passou a acompanhar o Git conforme o padrão CServer de
04/11. Corrigida a nota antiga que tratava SMTP XOAUTH2 como inexistente;
isso não comprova homologação no consumidor Vitrine.

## 2026-11-04 — Fila compartilhada de tarefas

- `.agents/tasks.md` passa a ser versionada, com referência relativa à governança CES; demais contextos privados continuam ignorados.
- Pendências anteriores foram organizadas sem executar seus escopos ou revalidar automaticamente estados antigos. Recuperação integral anterior permanece local, fora do Git.
- Validação documental: categorias, referências, UTF-8 e exceções de ignore; nenhuma alteração de runtime.
- Registros que já declaravam conclusão saíram da fila (conclusões anteriores, não novas implementações):
  - CMAIL-EXTRACTION — Captura por título, REGEX e janela recente.

Conciliação com `aacbd2f`: preservados o bug de viewport do UniServer, os
aceites locais de renderização/Gmail e a proposta de contas nomeadas.

## 26.11.3c — leitor para anotações

API pública `annotation_reader(owner_id)` com vínculo à identidade autorizada,
capacidade somente de leitura, janela/paginação Gmail e download de anexos
MIME aninhados. Nenhuma dependência do host/CCI, envio ou mudança de OAuth.
Contrato e limites em API.md. Dois testes focais e 340 testes de regressão
passaram; quatro testes foram pulados. A falha de toolbar móvel foi reproduzida
também no HEAD anterior e não integra esta entrega.

## 2026-11-03 — Contratos de apresentação e feedback

Template/assinatura adota slots fixos e ca.modal.v1. Feedback de aparência, leitor e navegação usa ca.messages.v1 do host; fallback nativo preservado. Quatro testes crosshost390/1440px,29regressões e7Node passaram, sem conta/envio real.

# Histórico do CMAIL

## 03/11/2026 — caminho canônico hospedado

CAW/CWH padronizam `/cm/cmail/auth/google/callback`; origem varia por host.
Teste de montagem e importação com esse prefixo, mantendo compatibilidade
ASGI com prefixos anteriores. Alteração de documentação/teste, sem mudar
versão, código de runtime, serviços ou cadastro Google nesta revisão.

## 26.11.3a — onboarding Gmail hospedado

Host pode autorizar administrador humano em `/setup` com principal existente,
CSRF e origem/callback ASGI explícitos. Upload de cliente Google Web limitado,
sem ecoar segredo; configuração inicial salva por CAS e segredo restrito.
Sem reinício automático, reset de grants ou OAuth implícito. Consentimento
usa o fluxo nativo após aplicação pelo operador. Sem hook,404 preservado.
Não implementa coleta de e-mails/anotações CCI nem altera fontes CWH.
Validação própria: 12 testes do onboarding, incluindo formulário no Edge e
consentimento simulado; regressão sem a suíte Playwright legada:332 aprovados.
Na suíte ampla inicial:336 aprovados e1 falha de toolbar em viewport estreita;
mesma falha reproduzida no baseline ac0fc46 (6 casos aprovados,1 falha).
Sem OAuth real, leitura de caixa, instalação global ou operação CWH nesta entrega.

Registros completos anteriores no Git, tag
`archive/docs-before-package-review-20261102`. Instalação e aceite pertencem
ao consumidor; este histórico não é inventário de máquinas.

## 2026-11-02 — documentação operacional

[Guia instalado](installed-package.md) e histórico conciso, sem alteração
de OAuth, configuração ativa, banco ou comportamento.

## 26.11.2b–e — Webmail e composição

Lista única standalone/CAW/CWH: pastas/busca/composição/itens compactos.
Leitor/compositor usam a área hospedada e ações/prévia/confirmação nativas.
Busca consulta provedor mais aproximações nas até 40 prévias recentes, sem
índice fuzzy integral. check-config --from-host usa ponteiro, não .env do CA.
Conexão e template têm rotas próprias. Fixtures adaptadas/coletadas não
comprovam aceite real de todos os modos/provedores.

## 26.11.2a — Google por capacidade

Drive/Docs/Sheets/Slides com consentimento incremental e grants por operação.
Escrita com prévia persistida, confirmação e claim único; sem replay incerto.
Gmail não concede Drive; testes sintéticos não comprovam OAuth/ação real.

## 26.10.30 — configuração, tema e manutenção

CmailConfiguration valida/edita por revisão e distingue salvo/ativo.
Rotas/provedores/persistência separados, prévias limitadas. Graph move aceita
201 Created. Tema pelo provedor de mesma origem mais próximo.

## 26.10.28–29 — aparência e renovação

Barra contextual/pastas; excluir fora da lixeira move, exclusão definitiva
confirma separadamente. Template/assinatura independentes com herança.
CID PNG/JPEG: até oito imagens/2 MiB. Microsoft offlineAccess opt-in,
cache ligado à identidade Windows; sessão local não prolonga token.

## 26.10.19–21 — Gmail por arquivo

Schema 1.2 gmail-file/authorized_user externo; 1.3 SMTP/XOAUTH2 explícito,
TLS/identidade, sem fallback automático. Schemas anteriores mantêm contrato.
Envio em duas fases/journal, sem retry incerto.

## 26.10.2–14 — extração e apresentação

Extração por assunto/remetente/tempo/REGEX, falha em ambiguidade; não marca
leitura nem registra valor sensível. Tema cm-* herdado ou base standalone.
Estado security/cmail/ por instância/owner; pacote não transporta tokens.
Encaminhamento Gmail/IMAP é texto, sem anexos; envio de anexos arbitrários
não é suportado. OAuth e execução real são aceites por consumidor.
