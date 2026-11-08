// Registry is shared by the live guide and compatibility audit.
export const componentCatalog = Object.freeze([
  {id: 'shell', name: 'Shell e navegação', selector: '.cui-shell', states: ['caw', 'cwh', 'mail'], tokens: ['canvas', 'surface', 'text', 'sidebar-surface', 'header-surface']},
  {id: 'menu', name: 'Menus por dados', selector: '.cui-menu-row', states: ['whatsapp', 'chat', 'email', 'agent', 'simple'], tokens: ['action', 'surface', 'muted']},
  {id: 'actions', name: 'Botões e ícones', selector: '.cui-button', states: ['primary', 'secondary', 'danger', 'disabled'], tokens: ['action', 'on-action', 'focus', 'danger']},
  {id: 'tabs', name: 'Abas', selector: '.cui-tabs', states: ['selected', 'keyboard'], tokens: ['action', 'border']},
  {id: 'form', name: 'Campos e formulário', selector: '.cui-form', states: ['normal', 'invalid', 'readonly', 'disabled'], tokens: ['surface', 'text', 'danger', 'focus']},
  {id: 'table', name: 'Tabela e paginador', selector: '.cui-table', states: ['sorted', 'filtered', 'empty', 'paged'], tokens: ['border', 'muted', 'surface']},
  {id: 'feedback', name: 'Mensagens e toast', selector: '.cui-message', states: ['info', 'success', 'warning', 'danger'], tokens: ['action', 'success', 'warning', 'danger']},
  {id: 'loading', name: 'Carregamento e progresso', selector: '.cui-progress', states: ['loading', 'cancelled', 'complete'], tokens: ['action', 'border']},
  {id: 'dialog', name: 'Modais e perguntas', selector: '.cui-dialog', states: ['confirm', 'alternatives', 'details'], tokens: ['surface', 'text', 'border']},
  {id: 'popover', name: 'Menu flutuante e tooltip', selector: '.cui-popover', states: ['open', 'closed', 'escape'], tokens: ['surface', 'border', 'text']},
  {id: 'metrics', name: 'Indicadores e funil', selector: '.cui-metrics', states: ['known', 'unknown'], tokens: ['action', 'muted', 'surface']},
  {id: 'conversation', name: 'Balões CCR oficial', selector: '.cui-conversation', states: ['incoming', 'outgoing', 'group', 'quote', 'continuation', 'reactions', 'rich'], tokens: ['surface', 'text', 'bubble-radius']}
]);
