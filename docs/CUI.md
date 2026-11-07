# Apresentação CUI

A branch `CUI` transfere os templates Jinja e CSS ao perfil `cmail`. O loader
consulta o snapshot declarado em `cmail/static/vendor/cui`, distribuído no wheel,
com autoescape e contexto Jinja preservados. Não exige um checkout vizinho.

`mailbox-navigation.mjs` conserva consulta, cancelamento, seleção e permissões;
as linhas são renderizadas pelo CUI com texto escapado pelo DOM. A bridge
`cui-navigation.mjs` é gerada e aponta para a release fixada no recibo.

OAuth, owner, CSRF, provedores, anexos, prévia, confirmação e resultados incertos
continuam no CMAIL. O conteúdo de e-mail conserva seu isolamento, incluindo
iframes de leitura/composição existentes. Esta migração não autoriza envios.

Guia canônico: `CUI/docs/uso/consumidores.md`. Compilar o perfil `cmail` e adotar
com `CUI/tools/adopt.py --package cmail --static static --module-bridge cui-navigation.mjs`.
Validar com `--check`, suíte sintética e Browser. Produção permanece separada.
