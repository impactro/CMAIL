# Testes do CMAIL — categorias e evidências

## Testes simulados

Nenhum destes grupos homologa uma conta real. SMTP, Graph, Gmail, tokens e
arquivos são sintéticos; testes de navegador estão separados pelo markerbrowser.

| Categoria | Diretório / seleção |
| --- | --- |
| IMAP/SMTP | `providers/imap`, `-m imap` |
| Gmail API / OAuth web | `providers/gmail/api`, `-m gmail_api` |
| Gmail API / OAuth por arquivo | `providers/gmail/oauth_file`, `-m gmail_file_api` |
| Gmail SMTP / XOAUTH2 por arquivo | `providers/gmail/oauth_smtp`, `-m gmail_file_smtp` |
| Outlook / Microsoft Graph / OAuth web | `providers/outlook`, `-m outlook` |
| Contratos compartilhados | `-m shared`: configuração, owners, anexos, prévias, registro, HTTP e Google Content |
| Interface simulada | `-m browser`; navegador e fixture de servidor próprios |

Alguns contratos cruzam provedores (MIME/Graph, anexos e isolamento): permanecem
compartilhados e são necessários além do diretório específico. Os markers
também classificam testes individuais desses contratos quando o nome identifica
um provedor. `shared` não significa ausência de importância para Gmail/Outlook.
Fixtures reutilizadas continuam centralizadas em helpers e módulos identificados;
nenhum caminho de checkout de uma máquina é fixado no teste.

```powershell
python -s -m pytest tests -m "simulated and not browser" -q
python -s -m pytest tests -m "simulated and gmail_file_smtp" -q
python -s -m pytest tests/providers/outlook tests/test_workspace_isolation.py -q
python -s -m pytest tests --collect-only -q
```

Suite integral inclui os testes de navegador e as pendências visuais antigas;
não a apresentar como equivalente à suite sem browser. A organização preservou
os382casos existentes, comparados por nome/parametrização sem perda/duplicação.
Não baixar browsers automaticamente para satisfazer esse comando.

## Homologação real — outra máquina

Instruções, pré-condições e recibo em
[validação distribuída](../docs/validation/README.md). `tests/live` é opt-in;
sem flag explícita é pulado e não lê plano/credenciais nem consulta provedores.
Não inferir que o Gmail disponível no LAB prova Outlook/IMAP/outras rotas.
