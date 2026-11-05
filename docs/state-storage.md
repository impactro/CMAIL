# Estado persistente do CMAIL

Padrão definido por Fábio em 01/11/2026: cada instância mantém o estado do
CMAIL em **`<raiz-da-instância>/security/cmail/`**. Vale para standalone e
composição CA/CAW/CWH. Não criar novos destinos por conveniência.

Com o JSON em `config/cmail.config.json`, configurar:

```json
"state": {"directory": "../security/cmail"}
```

Caminhos relativos partem da pasta do JSON, não do diretório de execução.
Se o host usar `config/cmail/`, ajustar para `../../security/cmail`.
Instâncias independentes não compartilham esse diretório. Os owners de uma
mesma composição continuam isolados pelo contrato nativo do CMAIL.

## Conteúdo e proteção

- `cmail.sqlite3`: banco persistente do componente.
- `security/google/`: segredo e tokens Google na estrutura interna nativa.
- `security/microsoft/`: estado de autenticação Microsoft, quando aplicável.
- `workspaces/`: arquivos persistentes geridos pelo módulo, quando aplicável.

A repetição em `security/cmail/security/google/` é intencional: o primeiro
`security` pertence à instância; o segundo é o layout interno atual do módulo.
Não achatar essa estrutura manualmente. O setup Google grava
`security/google/client-secret.txt` dentro de `state.directory`; o JSON contém
somente a referência ao arquivo. Banco e tokens não são lixo de migração.

Ignorar `security/` no Git; restringir acesso ao operador e à identidade do
serviço. Nunca registrar conteúdo de segredos, tokens ou e-mails em evidências.
Preservar a identidade Windows usada pelo DPAPI: mover o diretório não autoriza
transferir tokens para outro usuário ou host. Não usar `temp/`, `.agents/` ou
pastas de cache para estado ativo. Backups seguem o OPS do CServer, com
proteção equivalente, retenção e critério de restauração.

## Migração de uma instalação existente

1. Resolver a configuração efetiva e os caminhos atuais. Não inicializar uma
   conexão nova sobre uma instalação existente. Confirmar destino ausente.
2. Registrar a configuração anterior e o rollback em backup privado conforme
   OPS. Parar o serviço consumidor pelo mecanismo autorizado do host.
3. Mover integralmente o diretório de estado, preservando banco, eventuais
   arquivos SQLite auxiliares, tokens, subpastas e permissões. Não mesclar
   estados de contas nem mover um SQLite enquanto estiver em uso.
4. Validar e salvar com `CmailConfiguration` o novo `state.directory` e todas
   as referências de arquivos que apontavam para o diretório antigo. Conferir
   outros consumidores dessas referências sem revelar seus segredos.
5. Reiniciar o consumidor; validar saúde, configuração aplicada e uma leitura
   autenticada. Saúde/configuração não comprovam autorização OAuth. Não enviar
   e-mail nem revogar credenciais como teste de migração.
6. Em falha, parar o serviço, devolver o estado ao caminho anterior e restaurar
   a configuração correspondente antes de reiniciar. Nunca manter dois estados
   ativos concorrentes. Retirar apenas diretórios antigos comprovadamente vazios.

O parser conserva suporte a caminhos explícitos legados. O novo template não
migra instalações existentes automaticamente. Publicar fontes também não
atualiza o pacote instalado: verificar sua versão e seu template antes de
inicializar outra instância.

Referências: [configuração pelo host](configuration-host.md),
[bootstrap e migração](configuration-migration.md).
Referência opcional para mantenedores: CServer/CES/padroes/OPS-agent.md;
o checkout CServer não é dependência do pacote instalado.
