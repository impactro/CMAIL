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
