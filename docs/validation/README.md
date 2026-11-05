# Validação distribuída e instalação somente por pacote

## Papéis e artefatos

- DEV entrega commit, wheel/hash, documentação dessa revisão, exemplos JSON/MD
  e resultados simulados por categoria. Não declara homologação de outra máquina.
- Validador confere hash/versão e executa protocolos compatíveis com as contas
  disponíveis em seu host. Para validar a documentação, começa fora do checkout.
- OPS recebe a candidata validada e publica a mesma versão/hash, preservando
  estado e retorno. Registra processo, health e limites do aceite operacional.

Cliente recebe pacote e documentação, sem obrigação de Git, Node, build ou
checkout. Manual principal: [installed-package.md](../installed-package.md),
distribuído no wheel. Localizar por `pip show -f crania-cmail` ou metadata da
distribuição; não abrir implementação Python para descobrir variáveis.

Validação/inspeção completa de fontes usa o checkout ou archive imutável na
máquina de engenharia. Isso é distinto do cliente somente-pacote. Os testes
que inspecionam assets/fontes precisam desse artefato; não prometer que toda a
suite de engenharia funciona sem fontes. O bundle portátil abaixo valida os
contratos públicos e a leitura real sem levar implementação ao cliente.

## Composição do pacote de homologação

`python tools/build_validation_bundle.py --output <diretorio-de-temporarios>`
gera ZIP com manifesto SHA256, roteiro, plano exemplo e probes somente leitura.
Não contém tokens, contas reais, implementação, memória ou configuração ativa.
DEV também entrega o wheel e seu hash. Não armazenar segredos no ZIP ou no Git.

Na máquina validadora, usar seu Python canônico e instalação global autorizada:

```powershell
python -s -m pip install --no-user <wheel-aprovado>
python -s -m pip check
python -s -m pip show crania-cmail
python -s -m pytest tests/live -q
```

A última linha deve indicar skip e nenhuma conexão. Conferir hashes do ZIP
antes de extrair; trabalhar fora do checkout. Pytest é dependência da máquina
de validação, não nova exigência de runtime do cliente. Respeitar constraints
e conta do serviço do host; não criar outro Python/venv por conveniência.

## Plano privado e autorização

Copiar `live-plan.example.json` para a área privada do operador. Cadastrar
somente os perfis autorizados disponíveis. `configFile` é caminho absoluto de
configuração real já existente; nunca copiar tokens de outra máquina.
`ownerId` é o owner nativo existente, confirmado pelo administrador do host,
não nome inventado para fazer o teste passar. Não se fabrica sessão do browser.

| Campo por conta | Contrato |
| --- | --- |
| id | Rótulo de evidência sem dados pessoais, ASCII único. |
| profile | gmail_api, gmail_file_api, gmail_file_smtp, imap ou outlook. |
| configFile | Caminho absoluto do JSON nativo autorizado. |
| root | Raiz da instância quando necessária à composição. |
| connectorId | Só para ConnectorConfig2.0; omitido no caminho legado. |
| ownerId | Owner existente para Gmail web/Graph/IMAP; omitido em gmail-file. |
| folder | Pasta autorizada; padrão INBOX, Graph pode exigir ID da pasta. |
| messageId | Opcional: mensagem canário previamente acordada para leitura. |
| attachmentId / attachmentSha256 | Opcionais, junto do messageId; anexo canário/hash conhecido. |

Exemplo usa nomes fictícios. Remover perfis indisponíveis; registrá-los no
recibo como **não executados**, não aprovados. A configuração real deve ter
autorização/grant/DPAPI nativos válidos na conta que executará o probe. OAuth
interativo e consentimento são prévios e humanos, fora dessa suite.

## Execução explícita

```powershell
python -s -m pytest tests/live --run-cmail-live --cmail-live-plan <plano-privado.json> -m gmail_api -q --tb=short
python -s -m pytest tests/live --run-cmail-live --cmail-live-plan <plano-privado.json> -m outlook -q --tb=short
```

O comando com flag executa status e leitura reais: requer autorização do dono.
Não executá-lo automaticamente num SYNC. Filtra por perfil; use uma conta de
teste/canário. Não publicar saída com corpos, endereços, IDs reais ou traceback
com configuração. JUnit também pode conter dados privados: sanitizar antes do handoff.

## Matriz de aceite

| Perfil | Pré-condição | Prova automatizada | Limite |
| --- | --- | --- | --- |
| Gmail API/web | Grant Google/owner existente e callback cadastrado | Status, pastas, até3 resumos, canário/anexo opcionais | Não comprova callback concorrente nem entrega de envio. |
| Gmail API/arquivo | Tokenfile nativo local, conta correta, API habilitada | Mesmas leituras, operador local sem owner | Refresh normal pode atualizar estado nativo. |
| Gmail SMTP/XOAUTH2 | Tokenfile/SMTP/TLS existentes | Status/NOOP sem DATA | SMTP não lê caixa e não comprova recebimento de envio. |
| Outlook/Graph | Grant Microsoft/owner e consentimentos corretos | Status, pastas, resumos, canário/anexo opcionais | Não infere offlineAccess; expiração/reinício é cenário adicional. |
| IMAP/SMTP | Config/grant local e credenciais do host | Status e leituras IMAP/PEEK | Não executa SMTP DATA, MOVE, flags ou exclusão. |

Leitura pode renovar tokens/estado de conexão e gerar logs normais, mas o probe
não pede envio, marcação de lido, movimentação ou exclusão. Provedor sem leitura
de anexo reporta falha se esse cenário foi solicitado; não ocultar indisponibilidade.

Envio real é um protocolo separado: destinatário/conteúdo/arquivos explicitamente
autorizados, prévia conferida e execução única. Registrar aceitação separada
de entrega/recebimento; não repetir resultado incerto. Sem destinatário aprovado,
testar MIME/Graph sinteticamente. Callback, duas contas/owners, revogação,
prévia expirada, concorrência e rollback devem ser inspecionados pelo validador
conforme os contratos; esta suite não automatiza ações de autenticação ou administração.

## Recibo por ambiente

Registrar: host/conta operacional (sanitizados), Python e versões, commit/hash
do wheel e bundle, perfil/authMode/transporte, comandos, quantidade pass/fail/
skip/não executados, disponibilidade das contas, resultado canário, leitura
sem alteração observada, hashes de anexos e limitações. Revisor/operador assina
sua própria evidência; relatório DEV não substitui aceite independente.

No LAB, disponibilidade informada é Gmail. Nesta entrega nenhum perfil real
foi executado: organização e testes simulados não homologam a conexão local.
