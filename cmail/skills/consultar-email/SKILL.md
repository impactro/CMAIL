---
name: consultar-email
description: Consultar configuração, pastas e mensagens por meio do componente CMAIL.
---

# Consultar E-mail

Use `check-config` para validação offline e `status --live` somente quando uma
conexão real for necessária. `list-folders` e `list-messages` são leituras do
provedor configurado. Declare conta, pasta, limite e momento da consulta.

Resultado vazio vale apenas para a pasta e o limite testados. Não exponha senha,
arquivo de segredo, corpo de terceiros ou identificadores internos além do
necessário. A interface individual é iniciada por `serve` e permanece local.
