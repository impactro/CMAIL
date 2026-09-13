# Arquitetura CMAIL

```text
FastAPI standalone / subaplicação ASGI / API Python / Component Manager
             -> MicrosoftAuthService / GoogleAuthService -> OAuth + DPAPI
             -> MailService + Principal/capabilities
             -> Microsoft Graph, Gmail API ou IMAP/SMTP
             -> SQLite (identidades, sessões, listas, journal e auditoria mínima)
```

`config.py` aceita no `.env` somente `CMAIL_CONFIG_FILE`, valida o JSON fechado
de schema `1.1` (e lê `1.0` para rollback) e resolve caminhos relativos à pasta
desse JSON. Esse é o contrato standalone; em composição o host entrega
`configFile` e o módulo carrega o mesmo JSON diretamente, sem interpretar o
`.env` completo do agente. Segredos e
senhas nunca ficam no JSON: somente referências para arquivos externos.
`auth.py` mantém Microsoft SSO; `gmail.py`, Google OAuth e Gmail API; `setup.py`,
a configuração local unitária. `mail.py` isola demo/IMAP/SMTP; `graph.py`, o
Microsoft Graph. `store.py` é dono de identidades, sessões, preferências da
interface Webmail, listas, rascunhos e journal isolados por principal.
`service.py` aplica capacidades e impede repetição de rascunho consumido.
`api.py`, CLI e `web.py` reutilizam os mesmos casos de uso. `component.py`
entrega o par API Python + aplicação FastAPI, e o entry point
`crania_agent.component_apps` permite descoberta sem importar `ca.*`.

A UI é clara, responsiva e organizada como webmail: navegação por pastas,
lista de mensagens, painel de leitura e composição separada. Valores externos
são inseridos no DOM apenas por `textContent`; corpo de e-mail é solicitado ao
Graph como texto. A tela distingue demonstração, desconectado, reconexão,
desabilitado e conectado. Em composição, o OAuth sempre sai do `iframe` pela
janela principal.

No standalone, a raiz operacional e seu estado aceitam uma única identidade:
duas contas exigem duas pastas, dois JSONs/estados e duas portas. Não existe
seleção de conta nem multiplexação por `workspaceId` dentro de uma autoexecução.
Quando incorporado, o host entrega um
principal autenticado e o CMAIL vincula no máximo uma caixa por `workspaceId`,
isolando também listas, rascunhos e auditoria pelo mesmo dono. O assistente de
configuração local não é exposto nessa composição. O host nunca recebe token
OAuth e o módulo nunca confia em `workspaceId` enviado pelo navegador.

## Segurança

- interface somente em loopback;
- tenant/conta fixos, state OAuth, vínculo ao navegador, expiração e bloqueio de replay;
- sessão opaca server-side, cookie HttpOnly/SameSite e CSRF nos efeitos;
- cache OAuth por `tenant + subject`, protegido por DPAPI e fora de Git/JSON;
- senha/segredo fora do repositório e omitidos de status/log/API;
- todos os endpoints de dados exigem identidade; efeitos exigem CSRF;
- API Python exige `Principal` e capability, sem aceitar cookie/token web;
- CSP restritiva e saída DOM sem `innerHTML` para dados externos;
- HTML de e-mail não é renderizado;
- prévia e confirmação específica para todo envio;
- token de confirmação expira e é de uso único;
- falha SMTP após claim é incerta e bloqueia retry automático;
- auditoria guarda ação, estado e quantidade, não corpo, assunto ou destinatários.

O provider Microsoft Graph implementa obtenção de anexos, contatos, diretório,
calendários, disponibilidade e gestão confirmada de eventos. A fachada comum
retorna `NotImplementedError` quando o provider selecionado, como Gmail ou
IMAP, não oferece a capacidade. Proxy de imagem e editor HTML continuam fora
do módulo; campanhas permanecem uma evolução separada sobre o journal de
envios.

Logout revoga a sessão CMAIL. Desconectar remove o cache local DPAPI e revoga
as sessões da identidade; revogação global na Microsoft continua sendo ação da
conta/tenant. Rollback é desabilitar/remover o pacote da composição. O código e
os tokens atuais do CA permanecem intocados durante a homologação.
