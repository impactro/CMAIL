# Validação de e-mail pelo chatbot

## DEV-FSND — 06/11/2026

CMAIL26.11.6a (12aa1ab) e CA26.11.5j instalados no Python global do host.
O conector permanece dono da autenticação; o modelo recebe aliases e dados
da operação. Webmail mantém Gmail como padrão, sem seletor novo.

| Conta do consumidor | Pastas | Leitura | Busca ASCII | Template local |
|---|---:|---|---|---|
| Gmail | 25 | Um corpo obtido | Nativa,2 resultados | CrânIA |
| Dorotech IMAP | 8 | Um corpo obtido | Nativa,2 resultados | Dorotech |
| Outlook Microsoft IMAP | 23 | Um corpo obtido | Nativa,2 resultados | Lakatos |

Prévia local não é envio. Nenhuma mensagem foi transmitida, marcada, movida
ou apagada. Lixeira/mover/leitura tiveram validação sintética com gates de
capacidade, confirmação, expiração, integridade, conta e consumo único.

O Outlook recusou charset UTF-8: consulta ASCII passou sem charset explícito.
Consulta “Fábio” passou na26.11.6a com `native:false`, `incomplete:true`, janela
de40 resumos recentes e2 resultados. Não representa busca completa da caixa.

409 testes CMAIL sem navegador passaram na26.11.6; após a correção acentuada,
9 focais de busca/API passaram. CA:98 testes de integração e6 de gestão;
adaptador pessoal:31; CCR:10; leitor JavaScript:4. Conjuntos têm sobreposição.
As duas skills padrão e a skill pessoal passaram no validador de skills.
O bug visual preexistente de toolbar estreita continua na fila; essa bateria
não inclui os três arquivos de testes de navegador.

447 arquivos CA/CMAIL conferidos com os wheels.12 bancos íntegros e schemas
inalterados;158 configurações verificadas, somente2 alterações esperadas no
consumidor pessoal. Serviços voltaram saudáveis; três CWH conectados, sem
replay dos496 resultados incertos históricos do6121. CWH independente não
foi reiniciado. Configurações MonícIA/NICE não foram alteradas.

Aceite visual/chat real no Edge não foi executado: navegador externo não
acessível na sessão. Registrar como pendência do consumidor, sem apresentar
testes de API/SDK sintético como E2E visual. Recuperação e recibos privados
pertencem ao runtime consumidor, conforme o inventário OPS do host.
