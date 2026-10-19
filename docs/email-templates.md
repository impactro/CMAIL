# Templates E Fachada De Envio

Os templates editáveis pertencem ao consumidor em
`knowbase/mail/templates/<slug>.html`, descritos em `knowbase/mail/README.md`.
Essa pasta não guarda credenciais, conta de conexão, spool ou mensagens reais.
Nenhum template de pessoa/empresa faz parte do pacote genérico CMAIL.

Renderer público, sem rede, draft ou envio:

```python
from cmail import render_email_template

content = render_email_template(
    "knowbase/mail/templates/apresentacao.html",
    body="Alternativa em texto: apresentação para a empresa fictícia.",
    fields={"title": "Apresentação & próximos passos"},
    html_fields={"content": "<p>HTML local explicitamente revisado.</p>"},
)
# content == {"body": ..., "bodyHtml": ...}
```

Placeholders estritos `{{nome}}` aceitam letras, números e underscore, sem
expressões, atributos, includes, filtros ou execução de código. Campo ausente,
duplicado entre mapas, arquivo inválido ou HTML final acima de 200 mil
caracteres é recusado antes da preparação. Campos de `fields` são escapados;
somente `html_fields` insere HTML bruto explicitamente autorizado. Isso não é
sanitizador de HTML nem licença para publicar conteúdo recebido como confiável.
O texto alternativo `body` é obrigatório e preservado. Links, imagens remotas,
CSS e layout continuam sujeitos às limitações do cliente de e-mail; este
renderer não hospeda mídia, cria CID ou habilita anexos. Anexos são recusados.

## CLI Local

`python -m cmail.enviar --gmail` escolhe exclusivamente `gmail-file`, não uma
sessão Gmail web ou uma caixa inferida pelos destinatários.

```text
python -s -B -m cmail.enviar --gmail --config-file cmail.json --to recipient@example.com --subject "Apresentação" --body-file mensagem.txt --template knowbase/mail/templates/apresentacao.html --set "title=Apresentação" --html-field-file content=conteudo-revisado.html
```

`--to` é repetível; `--body` e `--body-file` são exclusivos. HTML pronto pode
entrar por `--html-file`, ou por `--template` com `--set chave=valor`,
`--set-file chave=arquivo`, `--html-field chave=html` e
`--html-field-file chave=arquivo`. Todos os arquivos são UTF-8.

Sem `--execute`, a saída JSON contém a **prévia exata** persistida, IDs e token
de confirmação. Mostre destinatários, assunto, texto e HTML finais à pessoa.
Após confirmação explícita desse rascunho, e não de um conteúdo reconstruído:

```text
python -s -B -m cmail.enviar --gmail --config-file cmail.json --execute --draft-id ID --confirmation-token TOKEN
```

Execução recusa novos destinatários, assunto, corpo, template ou campos: só
consome o snapshot do draft, mesmo que os arquivos originais tenham mudado.
Não existe flag que prepare e envie na mesma chamada. Falha após claim fica
incerta e não é repetida automaticamente. O usuário local deve proteger o token
de confirmação; não o publique em logs ou instruções compartilhadas.
