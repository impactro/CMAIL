# Manutenção e recursos do CMAIL

Revisão de 2026-10-30, componente `26.10.30a`, distribuição `26.10.30`.
Preparação do módulo para novos consumidores, incluindo o CWH. A integração
CWH e a homologação em caixas reais permanecem etapas posteriores.

## Organização do código

Inventário de Python, JavaScript, HTML e CSS: antes em `44f342f`; depois na
refatoração, já incorporando a correção Microsoft `6a2da93`. Linhas incluem
comentários e espaços. A separação reduz a concentração de responsabilidades;
o total cresce com os limites, colaboradores e verificações novos.

| Arquivo principal | Antes | Depois | Responsabilidade extraída |
| --- | ---: | ---: | --- |
| `cmail/web.py` | 780 | 203 | Rotas por domínio, identidade/CSRF e contexto HTTP |
| `cmail/service.py` | 585 | 488 | Principal/capabilities e calendário |
| `cmail/graph.py` | 489 | 341 | Transporte HTTP, política de rotas e DTOs |
| `cmail/gmail.py` | 467 | 195 | OAuth Google/DPAPI |
| `cmail/store.py` | 427 | 353 | Conexões, schema e migração SQLite |
| `cmail/mail.py` | 367 | 309 | MIME e listagem IMAP parcial |
| `cmail/appearance.py` | 364 | 294 | Sanitização HTML e mesclagem compartilhada |
| Código de produção total | 6.679 | 7.052 | Novos limites e módulos internos |
| Código de testes total | 2.670 | 3.016 | Suítes por domínio e regressões novas |

O antigo `tests/test_cmail.py`, com 912 linhas, foi distribuído entre
configuração, OAuth, Graph, serviço, componentes e isolamento de workspace.
Fixtures sintéticas ficam em `tests/helpers.py`. Os testes existentes foram
preservados. Não há arquivo de produção acima de 488 linhas nesse inventário.

## Recursos corrigidos

- **SQLite:** sair de `with Store.connect()` agora fecha a conexão depois de
  commit/rollback. O schema/migração é inicializado uma vez por identidade do
  arquivo, com nova inicialização se a base for recriada. O índice de auditoria
  atende filtro por owner e ordem decrescente. A expiração de rascunho passa a
  persistir antes de devolver erro; claim continua atômico e de uso único.
- **ASGI:** rede, SQLite, DPAPI e arquivos síncronos executam nos workers do
  host. `/health` não faz I/O e permanece disponível durante provider lento.
  Isso não aumenta automaticamente a concorrência admitida pelos providers.
- **Prévias:** cache em memória com até 64 entradas/16 MiB de conteúdo,
  até oito entradas por owner e quatro MiB por entrada. TTL de dez minutos,
  recolhido no próximo acesso; uso ocioso continua limitado pelo orçamento.
  Os limites contam os bytes do documento, não o overhead total do processo.
- **Entradas/transporte:** JSON de até oito MiB, após autorização e CSRF;
  leitura HTTP Google de até oito MiB e Graph de até dois MiB. Respostas de
  erro têm limite de 256 KiB. Excesso gera erro, sem truncar JSON silenciosamente.
- **IMAP:** a listagem pede FLAGS/BODYSTRUCTURE, até 16 KiB de cabeçalho e
  quatro KiB de texto com PEEK. Seleciona até 100 UIDs pelo fim da resposta,
  evitando criar um objeto Python para cada UID da caixa. O protocolo ainda
  entrega a resposta SEARCH inteira. Não baixa anexos completos na listagem.
- **Gmail:** lista metadados e os sete cabeçalhos usados pela UI. Mantém as
  requisições sequenciais; não introduz fan-out, retry ou cache de mensagens.
- **Imports:** exports públicos são carregados sob demanda. Importar `cmail`
  ou obter a API Python não carrega FastAPI até a aplicação web ser pedida.

Os fetches parciais seguem o [IMAP RFC 9051](https://www.rfc-editor.org/rfc/rfc9051.html#section-6.4.5).
A seleção de cabeçalhos usa o contrato de
[messages.get do Gmail](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/get).

## Medições locais

Execuções sintéticas com Python 3.12, sem rede, credenciais ou caixas reais.
`tracemalloc` mede alocações Python instrumentadas, não RSS. Tempos são
amostras locais, não SLA. Os JSONs de evidência ficam no staging ignorado
`.agents/temp/refactor-20261030/` e não contêm mensagens nem segredos.

| Experimento | Antes | Depois |
| --- | ---: | ---: |
| Mediana de 200 leituras `Store.history` | 6,829 ms | 1,034 ms |
| Crescimento de handles nessas leituras | +402 | 0 |
| Memória Python retida no loop | 596.864 bytes | 7.800 bytes |
| Pico ao selecionar últimos 50 de 100 mil UIDs | 4.591.350 bytes | 2.412 bytes |
| Import de `cmail` em processo novo, com instrumentação | 1.414,722 ms | 3,370 ms |
| Memória Python retida nesse import | 21.840.976 bytes | 238.915 bytes |

O benchmark SQLite desabilita GC somente durante o loop para tornar visível
a dependência anterior do coletor para liberar conexões. A rotina reativa GC
e recolhe objetos antes de remover sua própria pasta temporária. A comparação
de UIDs usa a mesma sequência sintética para ambas as implementações.
O ganho de import não representa inicialização completa do webmail: o custo
dos adapters passa a ocorrer quando eles são solicitados.

Reprodução a partir da raiz do repositório, usando o Python canônico do host
com user-site desativado:

```powershell
python -s -B -m tools.inspect_code --output .agents/temp/inventory.json
python -s -B -m tools.benchmark_resources --directory .agents/temp/benchmark --output .agents/temp/benchmark.json
python -s -B -m pytest tests -q
```

As ferramentas `tools/*` são de desenvolvimento e não entram no wheel.
O benchmark atual inclui import em processo novo; versões anteriores podem
ser medidas com o mesmo procedimento. Não comparar o histórico com um comando
que importe acidentalmente o pacote instalado em vez do fonte selecionado.

## Temporários e estado operacional

O inventário lê somente nomes, tamanhos e contagens nessas pastas, sem abrir
seu conteúdo. Fotografia antes de gerar o wheel desta versão:

| Pasta relativa | Arquivos | Bytes | Uso |
| --- | ---: | ---: | --- |
| `.agents/temp` | 32 | 708.559 | Staging, medições e evidências locais |
| `.agents/backup` | 341 | 4.525.854 | Backups de trabalhos anteriores |
| `build` | 39 | 376.238 | Cópia gerada para empacotamento |
| `dist` | 0 | 0 | Sem distribuição nessa pasta |
| `.pytest_cache` | 6 | 24.072 | Cache de desenvolvimento |

Essas contagens variam com build/testes. Nenhuma limpeza recursiva desses
diretórios foi feita nesta revisão. Remover staging/backups históricos exige
avaliar o que ainda é necessário para diagnóstico e rollback.

O benchmark remove apenas a pasta temporária que ele próprio cria. Prévias
HTML não geram arquivos. SQLite, WAL/SHM, journal, caches OAuth DPAPI,
configuração, arquivos de assinatura/template e logos são estado operacional;
não devem entrar em uma rotina genérica de remoção de temporários.
Rascunhos consumidos/expirados e auditoria ainda não têm expurgo automático:
retenção precisa ser definida com os consumidores antes de implementá-lo.

## Compatibilidade e preparação para o CWH

Os endpoints, nomes das rotas, envelopes, capabilities, entry points e
assinaturas públicas foram mantidos. `Principal` segue acessível por
`cmail`/`cmail.service`; OAuth Google continua reexportado por `cmail.gmail`;
helpers anteriores de Graph/MIME mantêm aliases. Os novos módulos internos
não devem ser usados como API de integração.

O compositor removeu branches de envio direto que já eram inalcançáveis;
usa preparação e execução por token. APIs públicas de resposta/encaminhamento
foram preservadas para consumidores existentes. Migrações SQLite legadas
continuam disponíveis; não se remove compatibilidade sem conhecer as bases
instaladas. Renovação Microsoft segue opt-in por `microsoft.offlineAccess`.

O CWH deve consumir `CmailApi`/`create_api`, receber um `Principal` validado
pelo host e respeitar capabilities/owner. O envio segue preparação, prévia e
execução com token de uso único. Não importar rotas, ler cookies, transportar
tokens OAuth ou contornar o journal. Configuração e aparência continuam
genéricas, sem importar identidade/regras particulares do CA ou de uma empresa.

## Validação e limites restantes

214 testes passaram após integrar a correção OAuth, incluindo navegador
headless, isolamento, confirmação de envio, exclusão contextual, templates,
conexões SQLite, concorrência do claim, orçamento de prévias e disponibilidade
do health com provider lento. Há um aviso de depreciação de Starlette/httpx
no ambiente de testes; não se alteraram dependências globais para suprimi-lo.

A abertura IMAP ainda carrega o RFC822 completo. O fetch parcial de listagem
pode produzir prévia vazia/incompleta em MIME complexo ou truncado; abrir a
mensagem mantém a leitura completa. Graph conserva o teto HTTP de dois MiB,
que pode impedir anexos maiores antes da validação de negócio de 25 MiB;
streaming de anexos não foi implementado. Gmail mantém uma consulta de
metadados por mensagem. O pool de workers depende do host e não há teste de
carga com tráfego real, medição de RSS ou expurgo de journal/auditoria.

Testes e build validam o fonte/pacote. Instalação e homologação no CA,
univ-server/PC-IA e Lakatos exigem verificar a versão carregada e o fluxo
autenticado em cada consumidor; não são comprovadas por este relatório.
