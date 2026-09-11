# Arquitetura CMAIL

```text
Flask / CLI / Component Manager
             -> MailService
             -> IMAP (leitura) / SMTP (envio)
             -> SQLite (listas, journal e auditoria mínima)
```

`config.py` lê o único `.env` da raiz de execução e resolve o segredo somente
por referência externa. `mail.py` isola os provedores. `store.py` é dono de
listas, rascunhos, tokens e journal. `service.py` impede repetição de rascunho
consumido. `web.py` usa os mesmos casos de uso da CLI.

## Segurança

- interface somente em loopback;
- cookie HttpOnly/SameSite e token CSRF nos efeitos locais;
- senha fora do repositório e omitida de status/log/API;
- HTML de e-mail não é renderizado;
- prévia e confirmação específica para todo envio;
- token de confirmação expira e é de uso único;
- falha SMTP após claim é incerta e bloqueia retry automático;
- auditoria guarda ação, estado e quantidade, não corpo, assunto ou destinatários.

O módulo ainda não implementa OAuth Microsoft/Google, download de anexo,
calendário nem exclusão de mensagem. Esses recursos exigem contratos separados,
revisão de permissões e aprovação de segurança antes de ativação real.

Rollback é desabilitar/remover o pacote da composição. A conta de e-mail não é
migrada nem alterada por instalar o módulo.
