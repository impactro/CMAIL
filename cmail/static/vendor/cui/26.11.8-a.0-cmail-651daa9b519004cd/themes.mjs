// Theme data never supplies executable HTML, JS, URLs or authorization.
export const themeContract = 'cui.theme.v1';
export const themeTokens = Object.freeze({
  canvas: 'color', surface: 'color', text: 'color', muted: 'color', border: 'color',
  action: 'color', link: 'color', 'on-action': 'color', focus: 'color', danger: 'color', success: 'color', warning: 'color',
  'sidebar-surface': 'color', 'sidebar-text': 'color', 'header-surface': 'color', 'header-text': 'color',
  radius: 'radius', 'bubble-radius': 'radius'
});
const color = /^#[a-f\d]{6}$/i, radius = /^(?:[0-9]|1[0-9]|2[0-4])px$/;
export function resolveThemes(catalog) {
  const byId = new Map(catalog.themes.map(theme => [theme.id, theme]));
  if (byId.size !== catalog.themes.length) throw TypeError('Tema duplicado.');
  const resolved = new Map();
  function resolve(id, chain = []) {
    if (chain.includes(id)) throw TypeError('Herança circular de tema.');
    if (resolved.has(id)) return resolved.get(id);
    const theme = byId.get(id); if (!theme) throw TypeError('Tema pai inexistente.');
    const parent = theme.extends ? resolve(theme.extends, [...chain, id]).tokens : catalog.defaults;
    const result = validateTheme({...theme, contract: themeContract, tokens: {...parent, ...theme.tokens}});
    resolved.set(id, result); return result;
  }
  return catalog.themes.map(theme => resolve(theme.id));
}
export function validateTheme(theme) {
  if (!theme || theme.contract !== themeContract || !/^[a-z][a-z0-9-]{0,63}$/.test(theme.id) || typeof theme.name !== 'string' || !['light', 'dark'].includes(theme.mode)) throw TypeError('Perfil de tema inválido.');
  if (!theme.tokens || Object.keys(theme.tokens).length !== Object.keys(themeTokens).length) throw TypeError('Mapa de tokens incompleto.');
  for (const [name, type] of Object.entries(themeTokens)) if (!(type === 'color' ? color : radius).test(theme.tokens[name] || '')) throw TypeError(`Token inválido: ${name}`);
  return theme;
}
export function applyTheme(root, theme) {
  validateTheme(theme); root.dataset.cuiTheme = theme.id; root.style.colorScheme = theme.mode;
  for (const name of Object.keys(themeTokens)) root.style.setProperty('--cui-' + name, theme.tokens[name]);
  // CCR and existing adapters retain their public token vocabulary.
  for (const name of Object.keys(themeTokens)) root.style.setProperty('--ca-ui-' + name, `var(--cui-${name})`);
  root.style.setProperty('--ca-chat-card-radius', 'var(--cui-bubble-radius)');
  root.style.setProperty('--ca-chat-bubble-radius', 'var(--cui-bubble-radius)');
  return () => {for (const name of Object.keys(themeTokens)) {root.style.removeProperty('--cui-' + name); root.style.removeProperty('--ca-ui-' + name);} root.style.removeProperty('--ca-chat-card-radius'); root.style.removeProperty('--ca-chat-bubble-radius'); root.style.removeProperty('color-scheme'); delete root.dataset.cuiTheme;};
}
