# Herança de apresentação CA/CWH

CMAIL `26.10.30f`, pacote `26.10.30.post5`. Implementação consumidora do
contrato focal alinhado com CA/CWH em 30/10/2026. Não inclui instalação nem
mudança de identidade, autorização, tema escolhido ou conta postal.

## Provedor e fronteira

O host publica no próprio documento:

```html
<html data-ca-theme-provider="cwh" style="color-scheme:dark">
```

O valor pode ser `ca` ou `cwh`. Os tokens efetivos ficam nesse html, não somente
no body. CMAIL escolhe o ancestral acessível de mesma origem **mais próximo**
com esse marcador. Na transição, CA legado com `.ca-shell` e `--ca-ui-text` no
html continua válido. Em CA → CWH → CMAIL, o CWH marcado governa o CMAIL, e o
próprio CWH decide como publicar os tokens que herdou do CA.

O marcador identifica somente um provedor de apresentação. Não é assertion,
capability, identificação de usuário ou permissão para alterar configuração.
A ponte não lê cookies/APIs/armazenamento de preferências nem escolhe empresa
ou caixa. Pai cross-origin/opaco é uma fronteira: conserva o fallback local,
sem postMessage geral nem mudança de CSP ou sandbox.

Um provedor marcado ainda sem `--ca-ui-text` conserva fallback local até publicar
seus tokens. Não pula esse provedor para buscar a identidade de um ancestral
mais distante. Mudanças de marcador/tokens redescobrem a fonte efetiva.

## Allowlist e tipos

Copiados com prefixo `--ca-ui-`: canvas, surface, surface-alt, text, muted,
border, action, on-action, focus, success, warning, danger, radius, space,
font, hover, selection e info. Nenhuma outra custom property é copiada.

O dicionário central e o mapa do ecossistema pertencem ao CA. No consumidor:

- `font` é font-family, não shorthand completo; o leitor preserva tamanho e
  line-height locais. `space` é uma dimensão CSS, base 16px; `radius`, dimensão.
- Cores e dimensões explícitas do host prevalecem. `on-action`, `success` e
  `warning` só são derivados quando ausentes; não recolorir a marca do usuário.
- `selection` alimenta a derivação local `--cm-soft`, com o fallback anterior
  text/surface quando não publicado. Tokens de chat incoming/outgoing não são
  necessários ao leitor/listagem de e-mails.
- O host publica uma paleta coerente, inclusive selection/text no escuro.
  O CMAIL não reescreve cores explícitas para tentar corrigir o tema do host.

Classes cm-*, IDs, larguras, grid, breakpoints e variáveis estruturais não foram
renomeados. Os aliases locais de paleta restantes continuam uma compatibilidade
interna, não um dicionário concorrente para os clientes.

## Atualização e limpeza

Observa nos htmls acessíveis até o owner: style, class, data-ca-theme, data-theme,
data-ca-theme-provider. Também escuta `ca:theme-change` em document/window e
load de assets. O evento apenas solicita releitura dos tokens do DOM; payload
de evento não transporta identidade, tema ou autorização.

Token retirado da fonte perde a cópia antiga. Quando o owner desaparece ou fica
inacessível, a ponte restaura os valores inline locais anteriores e a base do
módulo. pagehide desconecta observers/listeners e pageshow volta a descobrir a
fonte. Carregar o script duas vezes conserva uma única ponte.

A API anterior `window.CAFrameTheme.refresh()` / `.inherited()` foi preservada.
Ela informa estado visual, sem efeito sobre preferências ou permissões.

## CSS e conteúdo de e-mail

Folhas completas do CMAIL são do seu próprio documento/iframe; não devem ser
importadas diretamente no DOM do host. Os defaults :root e seletores legados
não são um contrato de microfrontend inline. O host usa a aplicação ASGI
montada e o iframe, conservando isolamento, assets e origem autorizada.

Fonte do corpo de leitura, bordas do editor e erro da aparência acompanham
tokens públicos. A prévia HTML enviada continua em iframe sandbox e conserva
as cores do e-mail/template: o tema do aplicativo não muda sua assinatura.
O ícone de erro de autenticação e alguns detalhes do CSS legado ainda têm
cores fixas; uma migração completa dessas superfícies é etapa posterior.
Não existe seletor ou persistência de tema novo no CMAIL.

## Validação reproduzível

```powershell
node --test tests/test_theme_bridge.cjs
python -s -B -m pytest tests/test_frontend_playwright.py -q
```

Os testes Node exercitam o JS real com DOM sintético: CWH explícito, CA legado,
ancestral mais próximo, owner tardio, token removido, evento comum, standalone,
fronteira opaca e cleanup/reentrada. Não usam rede nem identidade de usuário.

O navegador headless usa fixtures CA/CWH marcadas e CA legado, troca clara/escura,
tokens explícitos/font/radius, seleção e rascunho preservado. São cenários locais
sintéticos; não comprovam o tema ou instalação de um cliente real. Migração e
bootstrap de configuração são independentes deste pacote visual:
[contrato de migração](configuration-migration.md).

Nesta entrega, a suíte completa passou com 246 testes Python, incluindo sete
testes de navegador, e sete testes Node da ponte. Foram inspecionadas as
capturas sintéticas de CWH escuro e standalone claro. O wheel foi conferido
byte a byte com os 60 arquivos do módulo; não inclui testes nem staging.
Permanece o aviso conhecido de depreciação Starlette/httpx no ambiente de testes.
Nenhuma instância foi instalada/reiniciada e nenhum e-mail real foi operado.
