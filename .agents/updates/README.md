# Avisos de manutenção — CMAIL

## CMAIL-RENDER-CONTEXTUAL — revisão 1

- Handoff planejado, definido por Fábio em 01/11/2026. Não é entrega instalada.
- Fonte única: [pedido integrado CCR, revisão 2](../../../CCR/docs/progressive-history.md).
- Primeiro piloto: e-mail CMAIL integrado ao CWH; depois CAW. Mensagens na
  lateral existente, pasta em seletor no topo, Caixa de entrada inicial,
  leitura no conteúdo e ações autorizadas. Loading/erro/retry por região.
- CMAIL fornece adapter de pastas, mensagens, recursos e ações; preserva
  OAuth, owner, ACL, sanitização e referências de estado. Hosts e CCR não
  reimplementam o provedor. Ausência de mensagem selecionada não bloqueia pastas.
- Execução em outra máquina; candidata volta para inspeção aqui, depois teste
  de Fábio. Sem envio real, instalação ou reinício nesta publicação.
- security/cmail é padrão já aplicado, não tarefa deste handoff.
- Recuperação documental pelo Git; implantação futura exige artefato anterior.
