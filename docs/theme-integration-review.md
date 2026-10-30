# Herança visual CMAIL — levantamento para CA e CWH

Inspeção do runtime `a6e1088` / CMAIL 26.10.30c em 30/10/2026.
Este é o levantamento histórico. A ponte alinhada e seus limites atuais estão
em [herança de tema](theme-integration.md), a partir de 26.10.30f.
Não altera CSS/JS, temas, preferências, identidade de usuário ou autorização.
O dicionário e o mapa central pertencem ao CA (`VISUAL-IDENTITY.md` na raiz);
este documento registra o consumidor CMAIL e os pontos para integração.

## O que já funciona

As páginas completas carregam `style.css`, depois `cm-theme.css` e a ponte
`cm-theme.js`, com `body.cm-page.cm-webmail`. As classes públicas continuam
`cm-*`; SVG usa `currentColor`. Estrutura, IDs, seleção de mensagem e rascunhos
não devem mudar por uma troca de paleta.

A ponte atual procura um ancestral de mesma origem com `.ca-shell` e
`--ca-ui-text` no `documentElement`. Copia onze tokens básicos para o html do
iframe, acompanha mutações do html e desconecta o observer em pagehide.
Não lê APIs, cookies, credenciais nem conteúdo de mensagens do host. O teste
de navegador existente cobre CA sintético e mudança clara/escura sem perder
o rascunho; não cobre CWH como provedor de tema.

## Gaps concretos na base inspecionada

| Local | Comportamento observado | Consequência |
| --- | --- | --- |
| `cm-theme.js`, descoberta | Exige `.ca-shell` e tokens no html | CWH standalone com `.cwh-shell` não é reconhecido; CMAIL mantém fallback |
| `cm-theme.js`, leitura | Sempre lê `documentElement` | Tokens no body do host não sobem para o html; tema selecionado no body não é uma fonte válida hoje |
| `cm-theme.js`, observer | Só style/class/data-ca-theme do html e load de estilos | Não acompanha data-theme no body, marcador novo ou evento comum |
| `cm-theme.js`, cópia | Só grava tokens presentes | Se o host retirar um token, o valor inline antigo continua no iframe |
| `cm-theme.js`, semânticos | Recalcula on-action/success/warning | Cores semânticas explícitas do host são ignoradas |
| `cm-theme.js`, ciclo | Owner é escolhido uma vez; não há nova descoberta em start | Mudança tardia de provedor ou navegação que torna o pai inacessível precisa de tratamento no alinhamento |
| `cm-theme.css`, defaults | Declara `--ca-ui-*` e color-scheme light em :root | No iframe funciona como fallback; não importar essas folhas no DOM do host, onde poderiam sobrepor tokens globais |
| `style.css`, leitor | `reader pre` mantém shorthand font com Inter/Segoe | Cor herda, mas a fonte do corpo não acompanha completamente --ca-ui-font |
| `style.css`, erros/auxiliares | Auth error icon, cm-appearance-error e algumas bordas ainda têm cores fixas | Tema escuro/identidade podem divergir nessas superfícies |
| `style.css`, aparência | Há fallback de borda por --border e borda fixa da prévia | Mapear o contorno da UI para --ca-ui-border; --border não é token público do CA |

O branco do documento de prévia de e-mail não deve ser tratado automaticamente
como bug de tema: ele representa o HTML que será enviado, em iframe sandbox.
Separar borda/controles da UI das cores próprias do conteúdo da mensagem.
O template/assinatura pessoal não é seletor de identidade visual do aplicativo.

## Evidência sintética

Executar a ponte atual num contexto Node vm com documentos fictícios produziu:

| Ancestral simulado | Tokens no html | Herança |
| --- | --- | --- |
| `.ca-shell` | sim | sim |
| `.cwh-shell` | sim | não |
| `.ca-shell` | não | não |

No primeiro caso, um `--ca-ui-on-action` explícito não foi respeitado e um
focus removido da fonte permaneceu no iframe. Evidência local sem dados de
usuário: `.agents/temp/integration-20261030/theme-probe.json`. Não é conferência
visual nem teste de uma instalação real. O teste de navegador existente cobre
somente o cenário CA com tokens no html.

## Contrato focal proposto pelo responsável CWH

A proposta recebida preserva `--ca-ui-*`, sem criar uma API de identidade:

- Provedor explicita `html[data-ca-theme-provider="ca"|"cwh"]`, tokens no html
  e color-scheme efetivo. Marcador significa apenas apresentação.
- Consumidor escolhe o ancestral acessível de mesma origem mais próximo com
  esse marcador; reconhece CA legado `.ca-shell` + tokens no html na transição.
- Observar style, class, data-ca-theme, data-theme, data-ca-theme-provider e
  evento `ca:theme-change`, no elemento documentado pelo contrato comum.
- Copiar somente allowlist pública. Host é autoridade para on-action, success
  e warning; calcular fallback somente quando o token estiver ausente.
- Pai cross-origin/opaco conserva fallback local; não ampliar CSP/sandbox,
  usar postMessage geral ou buscar identidade/preferências de outro usuário.

Allowlist focal: canvas, surface, text, muted, border, action, on-action, focus,
success, warning, danger, radius, space e font, todos com prefixo `--ca-ui-`.
Extensões propostas: surface-alt, hover, selection e info. Tokens
`--ca-chat-incoming-background`/`--ca-chat-outgoing-background` são para chat;
o CMAIL não precisa adotá-los em uma lista/leitor de e-mails.

A proposta é compatível com o papel do CMAIL. Antes da implementação comum,
alinhar remoção de tokens (limpar cópia antiga e usar fallback), redescoberta
quando o owner mudar/ficar inacessível e prioridade de ancestral em CA → CWH →
CMAIL. Nenhum atributo pode autorizar usuário ou selecionar caixa/empresa.
O CWH deve publicar seus tokens já resolvidos no html mesmo quando o tema
legado ainda usa data-theme no body; isso é implementação do host.

## Mapa local de migração de paleta

Aliases existentes podem ser mantidos temporariamente enquanto os consumidores
migram; não renomear classes cm-*, IDs ou variáveis funcionais de layout.

| Uso/alias local | Token comum proposto |
| --- | --- |
| --blue | --ca-ui-action |
| --blue-soft, --cm-soft | --ca-ui-selection quando disponível; fallback mistura text/surface |
| --line | --ca-ui-border |
| --muted | --ca-ui-muted |
| --surface, --sidebar | --ca-ui-surface |
| texto sobre ação | --ca-ui-on-action |
| cm-appearance-error / cor de erro | --ca-ui-danger |
| reader pre font | --ca-ui-font preservando tamanho/line-height locais |

`--cm-soft` é hoje derivação de paleta, não uma instrução para remover todo
prefixo --cm-. Larguras, alturas, breakpoints, grid e outras variáveis
estruturais continuam sob responsabilidade do módulo. Não adicionar temas ou
persistência de preferências no CMAIL nesta fatia.

Aceite posterior: standalone sem host; CA legado; CWH standalone como owner;
CA com CWH intermediário; claro/escuro/marca; remoção de token; owner tardio;
pai inacessível; foco, contraste e rascunho preservado. Fazer testes técnicos
e inspeção visual separadamente. Migração de configuração continua prioritária.
