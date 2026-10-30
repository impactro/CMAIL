# Arquitetura CMAIL

```text
FastAPI standalone / subaplicação ASGI / API Python / Component Manager
             -> MicrosoftAuthService / GoogleAuthService -> OAuth + DPAPI
             -> MailService + Principal/capabilities
             -> Microsoft Graph, Gmail API ou IMAP/SMTP
             -> SQLite (identidades, sessões, listas, journal e auditoria mínima)
```

`config.py` aceita no `.env` somente `CMAIL_CONFIG_FILE`, valida o JSON fechado
dos schemas `1.0` a `1.3` e resolve caminhos relativos à pasta
desse JSON. Esse é o contrato standalone; em composição o host entrega
`configFile` e o módulo carrega o mesmo JSON diretamente, sem interpretar o
`.env` completo do agente. Segredos e
senhas nunca ficam no JSON: somente referências para arquivos externos.
`configuration.py` oferece ao host administrativo leitura/validação, edição por
revisão e o fragmento do catálogo CES. Novas instâncias usam `config/` e pares
JSON/MD. Salvar não substitui o Config imutável em uso nem reinicia o host.
Contrato: [configuração pelo host](docs/configuration-host.md).
`auth.py` mantém Microsoft SSO; `google_auth.py`, Google OAuth/DPAPI;
`gmail.py`, somente operações da caixa Gmail; `setup.py`, a configuração local
unitária. Os nomes públicos anteriores de Google continuam reexportados por
`gmail.py`. `mail.py` isola demo/IMAP/SMTP, apoiado por `mime_read.py` e
`imap_listing.py`. `graph.py` contém o provider Outlook; transporte e DTOs ficam
em `graph_http.py` e `graph_models.py`. `store.py` é dono de identidades, sessões, preferências da
interface Webmail, listas, rascunhos e journal isolados por principal.
`database.py` inicializa schema uma vez por arquivo e fecha as conexões ao sair
do contexto, com commit/rollback. `service.py` aplica capacidades e impede
repetição de rascunho consumido; delega calendário a `calendar_service.py`.
Identidade/capacidades ficam em `principal.py`, reexportadas pelos caminhos antigos.
`api.py`, CLI e `web.py` reutilizam os mesmos casos de uso. `web.py` monta a
aplicação; `web_auth`, `web_setup`, `web_mail`, `web_calendar` e `web_appearance`
registram as rotas. `web_security` aplica identidade/CSRF e `web_context`
centraliza JSON limitado e execução no pool de workers. `component.py`
entrega o par API Python + aplicação FastAPI, e o entry point
`crania_agent.component_apps` permite descoberta sem importar `ca.*`.

A UI é clara, responsiva e organizada como webmail: navegação por pastas,
lista de mensagens, painel de leitura e composição separada. Valores externos
são inseridos no DOM apenas por `textContent`; corpo de e-mail é solicitado ao
Graph como texto. A tela distingue demonstração, desconectado, reconexão,
desabilitado e conectado. Em composição, o OAuth sempre sai do `iframe` pela
janela principal.

A barra `cm-message-actions` fica no cabeçalho e acompanha a seleção atual.
Ícones SVG locais usam `currentColor`, nomes acessíveis e os tokens públicos
do tema; o contrato permanece `cm-*`, sem importar assets privados do host.
Respostas de leitura antigas são descartadas ao trocar a seleção/pasta. O
compositor conserva a mensagem de origem ao navegar. A disponibilidade de
ações vem do serviço, combinando provider e capacidades do principal.
No IMAP, ações usam UID e pasta explícita. Movimentação usa UID MOVE ou
COPY/STORE/UID EXPUNGE, sem EXPUNGE geral; falha interrompe sem repetição.
CAPABILITY é consultado após autenticar, evitando o cache anterior ao LOGIN.
`trash_message` e `delete_permanently` são casos de uso distintos, com
`mail.manage` e auditoria próprias. Somente exclusão definitiva exige
confirmação; mover para a lixeira é imediato. O botão Excluir conserva
ícone/cor e escolhe a operação pelo contexto da pasta. Exclusão definitiva
exige lixeira reconhecida no serviço; Graph/Gmail também verificam a pertença
real da mensagem, e IMAP opera somente no UID da pasta selecionada.

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
- corpo recebido é apresentado como texto; prévias de saída usam CSP e sandbox;
- prévia e confirmação específica para todo envio;
- token de confirmação expira e é de uso único;
- falha SMTP após claim é incerta e bloqueia retry automático;
- auditoria guarda ação, estado e quantidade, não corpo, assunto ou destinatários.

O provider Microsoft Graph implementa obtenção de anexos, contatos, diretório,
calendários, disponibilidade e gestão confirmada de eventos. A fachada comum
retorna `NotImplementedError` quando o provider selecionado, como Gmail ou
IMAP, não oferece a capacidade. Templates/assinaturas têm editor HTML próprio;
proxy de imagens recebidas e campanhas permanecem fora dessa superfície.

## Recursos e fronteiras de execução

Os providers continuam síncronos. A borda HTTP usa endpoints síncronos ou
`run_in_threadpool` para I/O de rede, DPAPI e arquivos; o health permanece
assíncrono e não faz I/O. O pool é administrado por Starlette/host, sem criar
um pool por conta, aumentar concorrência ou repetir operações automaticamente.

`PreviewCache` guarda bytes, no máximo 16 MiB/64 entradas por aplicação,
4 MiB por prévia e oito entradas por proprietário, por dez minutos. Expiração
é recolhida no próximo acesso; não há thread de limpeza nem arquivos de prévia.
O JSON de entrada é limitado a oito MiB após validar identidade e CSRF.
Leituras HTTP Google são limitadas a oito MiB; Graph mantém o limite de dois
MiB, agora com erro explícito em vez de truncar silenciosamente JSON.

Listagem IMAP usa PEEK parcial: cabeçalho de até 16 KiB, texto de até quatro
KiB e BODYSTRUCTURE para o indicador de anexo. Corpo completo e inventário
ficam na abertura da mensagem. Gmail lista metadados e somente os cabeçalhos
usados na interface, mantendo a sequência de requisições do provider.

`cmail.__init__` carrega exports por demanda: a API Python não importa o
FastAPI até o consumidor pedir a aplicação web. O CWH deve usar a fachada
`CmailApi`, o principal validado pelo host e o journal em duas fases; sua
integração não deve importar rotas nem transportar cookies/tokens OAuth.
Métricas, limites e inventário de temporários: [manutenção](docs/maintenance.md).

Logout revoga a sessão CMAIL. Desconectar remove o cache local DPAPI e revoga
as sessões da identidade; revogação global na Microsoft continua sendo ação da
conta/tenant. Rollback é desabilitar/remover o pacote da composição. O código e
os tokens atuais do CA permanecem intocados durante a homologação.
