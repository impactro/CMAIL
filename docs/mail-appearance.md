# Template e assinatura

Componente 26.10.30a, distribuição 26.10.30. Independente do CA; nenhum
nome, marca ou contato de cliente pertence ao pacote genérico.

Template envolve a mensagem com testeira, moldura e rodapé; assinatura é um
bloco independente. Ambos admitem `inherit`, `none`, `default` (modelo CMAIL)
ou `custom`. O padrão usa os dois em novas mensagens e somente assinatura em
respostas/encaminhamentos. Cada mensagem pode fazer uma escolha pontual.

## Modal e arquivos

“Configurar template e assinatura” oferece seletores por contexto, dados
pessoais, cores e logo. Um PNG/JPEG com CID `logo` entra automaticamente na
assinatura padrão. “Avançado” permite importar/editar HTML, adicionar imagens
e preencher outros campos textuais em JSON. “Restaurar herança” muda a edição;
Salvar aplica. “Visualizar” não prepara nem envia e-mail.

A herança é resolvida sem copiar padrões: sistema → empresa → pessoa → escolha
da mensagem. Alterações da empresa chegam a quem continua herdando. Preferências
pessoais só substituem os campos/escolhas declarados.

- Empresa: `mail/company/profile.json`, relativo à raiz operacional.
- Standalone sem proprietário: `mail/personal/profile.json`.
- Host com resolver: `<workspace>/mail/profile.json`.
- Host sem resolver: `<state>/workspaces/<hash-do-owner>/mail/profile.json`.

O modal mostra a pasta pessoal efetiva. Uploads são gravados em `assets/` com
nomes pelo hash e referidos pelo perfil. Arquivos antigos não são apagados
automaticamente. Arquivos operacionais não entram no Git do módulo.

```json
{
  "schemaVersion": "1.0",
  "modes": {
    "new": {"template": "custom", "signature": "custom"},
    "reply": {"template": "none", "signature": "inherit"},
    "forward": {"template": "inherit", "signature": "inherit"}
  },
  "fields": {"company_name": "Empresa de exemplo", "sender_name": "Pessoa de exemplo"},
  "templateFile": "email.html",
  "signatureFile": "assinatura.html",
  "assets": [{"contentId": "logo", "file": "assets/logo.png"}]
}
```

`templateHtml`/`signatureHtml` recebem HTML diretamente como alternativa aos
arquivos. Omissão herda; salvar `{}` restaura tudo. A empresa é administrada
pelo host; o modal só grava preferências pessoais.

## Mesclagem e imagens

Campos `{{nome}}` são texto escapado, sem expressões, includes ou execução.
O template contém exatamente um `{{body_html}}`. `{{signature_html}}` define
a posição da assinatura; se ausente, a assinatura é anexada ao miolo uma única
vez. `{{logo_html}}` é o logo opcional. `{{title}}` vem do assunto.
`{{reply_quote_html}}` é reservado e atualmente vazio: histórico pertence ao
provedor. Esses campos não podem ser sobrescritos pelo mapa textual do perfil.

Campos padrão: `sender_name`, `sender_role`, `sender_phone`, `sender_email`,
`company_name`, `header_bg`, `header_accent`, `footer_notice`. Nome/e-mail partem
da identidade quando disponíveis. Outros textos podem ser fornecidos em
`fields`. Campo ausente falha antes da preparação. As cores exigem `#RRGGBB`;
links renderizados aceitam HTTP/HTTPS, mailto e tel. O HTML usa uma allowlist
de elementos/atributos de e-mail. Scripts, eventos, iframes, CSS com URLs e
imagens remotas são recusados. Importar modelos com estilos inline, sem `<style>`.

Imagens usam `src="cid:identificador"`, relacionado a `assets`. Na API de
salvamento, uma imagem aceita `file` relativo ou `contentType`/`contentBase64`,
com `name` opcional. PNG/JPEG, oito imagens, dois MiB no conjunto; perfil até
quatro MiB, HTML final até 200 mil caracteres. Caminhos externos são recusados.
O transporte usa [inlineImages](inline-images.md), com bytes no snapshot.

Ao importar HTML legado com assinatura fixa, escolher assinatura “Nenhuma” ou
separar o bloco em `signatureFile`. O renderer não adivinha os dados pessoais.

## API, confirmação e host

API Python: `appearance(principal)`, `save_appearance(principal, profile)` e
`render_appearance(principal, payload)`, com `mail.send`. Para aplicar aparência,
usar `prepare_send(principal, {..., "appearance": {}})`. HTML pronto continua
aceito em `bodyHtml` sem aparência; misturar ambos é recusado para evitar dupla
aplicação. Execução mantém o contrato `execute_send` e token de uso único.

`prepare_message_action(principal, id, payload)` requer `mail.send` e `mail.read`;
`kind` é `reply`, `replyAll` ou `forward`, com `body`, `folder`, `appearance`
opcional e `recipients` no encaminhamento. Os endpoints antigos são preservados.
A prévia das ações mostra o conteúdo adicionado; o provedor trata o histórico.
Gmail/IMAP continuam encaminhando texto sem anexos originais.

HTTP: GET/PUT `/api/appearance`, POST `/api/appearance/preview`, POST
`/api/messages/{id}/prepare`, POST `/api/send/prepare` e `/api/send/execute`.
Escritas e prévias exigem CSRF; proprietário não vem do payload. Prévias ficam
em memória, isoladas por proprietário, até dez minutos: 64 por aplicação,
oito por proprietário, 16 MiB no total e quatro MiB por prévia. Expiração é
recolhida no próximo acesso, sem thread de manutenção nem escrita em disco.
A rota HTML tem CSP própria e iframe sandbox sem scripts/formulários/rede.

Factories Python/ASGI aceitam serviços opcionais do host:

- `mailWorkspaceRootResolver(owner_id)`: pasta privada do proprietário validado;
  CMAIL acrescenta `mail/`. O CA fornece a resolução canônica, sem paths do cliente.
- `mailCompanyRoot`: pasta do perfil empresarial fornecida pela composição.

O rascunho guarda HTML/imagens finais. Alterar os arquivos depois de preparar
não muda o envio confirmado; executar não refaz mesclagem. Não há retry automático.

## Autenticação

O webmail mostra Outlook/Gmail conectado depois de carregar as pastas.
Token Microsoft inválido ou HTTP401 do Graph marca `reauthorize` no estado
compartilhado e devolve `requiresReconnect`/`reauthorizeUrl`. A reconexão sobe à
janela principal quando incorporada. Timeout, HTTP403 e HTTP503 não revogam
conta nem solicitam novo consentimento. Escopos OAuth permanecem inalterados
sem o opt-in administrativo de `microsoft.offlineAccess`, documentado no README.

Graph rico usa `message.body`, sem combinar com `comment`, conforme os
contratos oficiais de [reply](https://learn.microsoft.com/en-us/graph/api/message-reply?view=graph-rest-1.0)
e [forward](https://learn.microsoft.com/en-us/graph/api/message-forward?view=graph-rest-1.0).
