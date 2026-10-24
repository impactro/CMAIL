# Gmail Por Arquivo — 26.10.21a

## Transporte SMTP explícito

Schema `1.3`, modo `gmail-file`, mantém os campos do schema `1.2` e exige
`gmailFile.transport`, com valores `api` ou `smtp`. O schema `1.2` permanece
inalterado e seleciona API. Exemplo sanitizado: `config.gmail-smtp.example.json`.

```json
"gmailFile": {
  "account": "sender@example.com",
  "tokenFile": "security/google-authorized-user.json",
  "transport": "smtp"
}
```

SMTP conecta exclusivamente a `smtp.gmail.com:587`, exige STARTTLS com validação
do certificado e autentica a caixa configurada por SASL XOAUTH2. O servidor
confirma que aquele token pode acessar aquela caixa; não se presume identidade
pelo conteúdo do arquivo. `status` faz AUTH/NOOP e não transmite mensagem.
Não usa `/profile`, não precisa habilitar Gmail API e nunca troca de transporte
após um erro. O token precisa do grant SMTP `https://mail.google.com/`.
Renovação continua em memória e não reescreve o token legado.

Para consentimento novo, acrescentar `--transport smtp` a `auth`/`init`:

```text
python -s -B -m cmail.gmail_file auth --transport smtp --client-file security/google-desktop-client.json --token-file security/google-authorized-user.json --account sender@example.com
python -s -B -m cmail.gmail_file status --config-file cmail.json
python -s -B -m cmail.gmail_file refresh --config-file cmail.json
```

O consentimento SMTP pede o grant próprio e valida AUTH antes de criar um arquivo
novo; PKCE/state/loopback e recusa de sobrescrita permanecem. Não inicia consentimento
automaticamente em uso normal. Não revoga nem amplia grants existentes.

`cmail.enviar --gmail` conserva a preparação e execução confirmada do mesmo draft.
O journal separa conta **e transporte**: um draft de API não pode ser consumido
por SMTP. HTML e texto alternativo são preservados; lista de destinatários usa
envelope Bcc. Aceitação SMTP significa submissão, não entrega ou leitura.
Falha/recusa parcial após claim fica incerta e não permite replay. Erro em QUIT
depois da aceitação de DATA não faz repetir uma mensagem aceita.

Este transporte oferece somente envio. Leitura, pastas, resposta/encaminhamento
com busca de mensagem e montagem web continuam indisponíveis nesse modo;
não existe fallback para API/IMAP. O transporte API original conserva suas funções.

Referências oficiais: [SMTP Gmail](https://developers.google.com/workspace/gmail/imap/imap-smtp)
e [SASL XOAUTH2](https://developers.google.com/workspace/gmail/imap/xoauth2-protocol).

## Transporte API original

Distribuição Python mínima: `crania-cmail>=26.10.19`. Esta é uma candidata em
fonte; não comprova instalação, consentimento ou envio em uma conta real.

## Contrato

`config.gmail-file.example.json` demonstra o schema fechado `1.2`, modo
`gmail-file`. Os schemas `1.0` e `1.1` e os modos existentes permanecem aceitos.
O novo objeto obrigatório desse schema é `gmailFile`, com `account` (remetente
esperado) e `tokenFile` (referência externa). Caminhos relativos partem do JSON.
O `.env` opcional do executável geral continua contendo somente
`CMAIL_CONFIG_FILE`. Com `Config.from_file`, não é necessário criar esse `.env`.

O arquivo `authorized_user` contém `client_id`, `client_secret`, `refresh_token`,
e opcionalmente `token`, `expiry`, `scopes` e `token_uri`. O campo `type` pode
ser omitido nos arquivos legados ou ser `authorized_user`; outros tipos falham.
Não é uma senha SMTP nem uma conta de serviço. Não copiar esse arquivo para
Git, template, agente, log ou resposta. Ele permanece no local privado indicado.

O CMAIL não acredita no endereço escrito dentro do token: confere a caixa real
por [users/me/profile](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users/getProfile)
antes de liberar o bearer para a operação. A conta deve coincidir exatamente,
sem inferir remetente pelo destinatário ou aceitar aliases por semelhança.
O grant precisa permitir a leitura do perfil Gmail e a operação solicitada;
um token apenas com `gmail.send` pode não permitir a confirmação da identidade.
Além do grant, a Gmail API precisa estar habilitada no projeto Google do cliente.
Um token que funciona no SMTP legado pode renovar e ainda receber `403
SERVICE_DISABLED` nessa API. Nesse caso esta candidata bloqueia o uso: não
omite a conferência de conta nem muda automaticamente para SMTP. Uma opção
SMTP XOAUTH2 exige a seleção explícita descrita acima; não é fallback desta rota.

## API Local

```python
from cmail import Config, Principal, create_api

api = create_api(Config.from_file("cmail.json"))
operator = Principal.local_operator()
status = api.status(operator, live=True)
preview = api.prepare_send(operator, {
    "recipients": ["recipient@example.com"],
    "subject": "Apresentação",
    "body": "Alternativa em texto.",
    "bodyHtml": "<p>Apresentação revisada.</p>",
})
# Só depois de exibir e confirmar especificamente essa prévia:
# api.execute_send(operator, preview["draftId"], preview["confirmationToken"])
```

Preparar não consulta provedor nem envia. A prévia indica o remetente configurado;
somente `status(live=True)` e a execução validam a conta no Google. O journal é
isolado pelo remetente configurado: trocar a conta não permite consumir um
rascunho anterior. O token de confirmação é unitário e expira em dez minutos.
Após claim, falha permanece `uncertain`, sem retry automático. A execução usa
exatamente o conteúdo gravado; não relê um template modificado.

O modo é headless e local: `identity_id`, `email` e `owner_id` arbitrários são
recusados. `principal_for_owner`, montagem web/ASGI e factory de composição por
host não servem como atalho para essa conta. Hosts web continuam usando os
modos OAuth existentes com `Principal` autenticado pelo próprio host.

## Inicializar E Renovar

Comando explícito para um novo consentimento Google Desktop:

```text
python -s -B -m cmail.gmail_file auth --client-file security/google-desktop-client.json --token-file security/google-authorized-user.json --account sender@example.com
```

`init` é alias de `auth`. O comando fornece a URL, espera o usuário autorizar
no navegador externo e recebe o código em listener efêmero **127.0.0.1**, por
até 300 segundos (`--timeout`, de 1 a 600). Não abre navegador automaticamente.
Usa state, PKCE S256 e callback loopback do fluxo Desktop suportado, sem OOB,
SSO do CA ou sessão web CMAIL. O arquivo do cliente precisa ter objeto `installed`.
Falha/conta divergente não gera token. Um arquivo existente nunca é sobrescrito.

Escolha uma pasta privada existente, com ACL do operador, antes de iniciar.
O arquivo novo é criado exclusivamente com modo restrito onde suportado; no
Windows a proteção real depende da ACL herdada. O comando não modifica ACLs.

```text
python -s -B -m cmail.gmail_file status --config-file cmail.json
python -s -B -m cmail.gmail_file refresh --config-file cmail.json
```

`status` renova se necessário; `refresh` força renovação silenciosa. Ambos usam
somente memória: não reescrevem o arquivo legado. Não abrem navegador nem
iniciam consentimento quando o token expira/revoga. A próxima execução pode
renovar novamente a partir do mesmo refresh token. Erros exigem decisão humana
e `auth` explícito quando necessário, não fallback para outra conta.

Renovação usa sempre `https://oauth2.googleapis.com/token`, sem redirects. O
campo legado `token_uri` só aceita esse endereço ou o antigo endpoint oficial
`https://accounts.google.com/o/oauth2/token`; nunca direciona a credencial a uma
URL arbitrária. Códigos, tokens, callbacks e corpos de erro do provedor não são
registrados. Veja o [fluxo Desktop Google](https://developers.google.com/identity/protocols/oauth2/native-app).

## Componentes Da Implementação E Validação

- `gmail_file.py`: leitura limitada, refresh em memória, identidade e CLI.
- `gmail_consent.py`: consentimento explícito, callback e criação de arquivo novo.
- `enviar.py`: fachada de duas fases; [templates](email-templates.md).
- `template_render.py`: renderer público local, sem transporte nem provedor.

`python -s -B -m pytest -q` cobre fixtures sintéticas e provedores simulados.
Os testes não validam credencial de produção, consentimento real, entrega no
Gmail ou aparência do HTML em um cliente de e-mail.
