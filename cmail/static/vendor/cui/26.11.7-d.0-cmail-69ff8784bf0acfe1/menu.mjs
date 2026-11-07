/* CUI menu: normalized data and host callbacks, no transport or product schema. */
export function selectItems(items, query = '', limit = 80) {
  const match = query.trim().toLocaleLowerCase('pt-BR');
  const filtered = match ? items.filter(item => (item.title + ' ' + (item.subtitle || '')).toLocaleLowerCase('pt-BR').includes(match)) : items;
  return {items: filtered.slice(0, limit), total: filtered.length};
}

export function renderRows(root, source, items, selected = '', {resolveAsset} = {}) {
  if (!['whatsapp','chat','email','agent','simple'].includes(source.layout)) throw new TypeError('Layout de menu inválido.');
  const doc = root.ownerDocument, fragment = doc.createDocumentFragment();
  const focused = root.contains(doc.activeElement) ? doc.activeElement.dataset.item : '';
  const make = (tag, cls, value) => {
    const node = doc.createElement(tag);
    // cui-* is canonical; ca-* aliases keep the existing adopter compatible.
    node.className = cls.replace(/\bca-/g, 'cui-') + ' ' + cls;
    if (value !== undefined) node.textContent = String(value);
    return node;
  };
  for (const item of items) {
    const button = make('button', 'ca-menu-row'); button.type = 'button';
    button.dataset.item = item.id; button.setAttribute('aria-pressed', String(item.id === selected));
    const avatar = make('span', 'ca-menu-avatar', item.icon || item.title.slice(0, 2).toUpperCase());
    if (item.avatar && resolveAsset) {
      try {
        const url = resolveAsset(item.avatar, {document: doc, source, item});
        if (url) {
          const img = make('img', 'ca-menu-avatar-image'); img.src = String(url);
          img.alt = ''; img.loading = 'lazy'; avatar.replaceChildren(img);
        }
      } catch { /* Host denial retains the local initials. */ }
    }
    const body = make('span', 'ca-menu-row-body');
    body.append(make('strong', 'ca-menu-title', item.title), make('span', 'ca-menu-subtitle', item.subtitle || ''));
    const markers = make('span', 'ca-menu-markers');
    for (const marker of (item.markers || []).slice(0, 8)) {
      const tone = ['accent','success','warning'].includes(marker.tone) ? marker.tone : 'neutral';
      const dot = make('span', 'ca-menu-dot ' + tone, '●');
      dot.title = marker.label; dot.setAttribute('aria-label', marker.label); markers.append(dot);
    }
    body.append(markers);
    const meta = make('span', 'ca-menu-meta');
    if (item.timestamp) {
      const date = new Date(typeof item.timestamp === 'number' ? item.timestamp * 1000 : item.timestamp);
      if (!Number.isNaN(date.valueOf())) meta.append(make('time', 'ca-menu-time', date.toLocaleDateString('pt-BR')));
    }
    if (item.pinned || item.favorite) meta.append(make('span', '', `${item.pinned ? '⌖' : ''}${item.favorite ? '♥' : ''}`));
    if (Number.isSafeInteger(item.unread) && item.unread > 0) meta.append(make('span', 'ca-menu-unread', item.unread > 999 ? '999+' : String(item.unread)));
    button.append(avatar, body, meta); fragment.append(button);
  }
  root.dataset.layout = source.layout; root.replaceChildren(fragment);
  if (focused) [...root.children].find(node => node.dataset.item === focused)?.focus({preventScroll: true});
}

export function mountMenu({root, search, more, status, onSelect, loadItems, resolveAsset}) {
  if (typeof loadItems !== 'function' || typeof onSelect !== 'function') throw new TypeError('Callbacks do menu obrigatórios.');
  let source, items = [], selected = '', generation = 0, limit = 80, disposed = false, controller;
  const states = new Map();
  function paint() {
    const visible = selectItems(items, search.value, limit);
    renderRows(root, source, visible.items, selected, {resolveAsset});
    more.hidden = visible.items.length >= visible.total;
    more.textContent = `Carregar mais · ${visible.items.length} de ${visible.total}`;
    status.textContent = visible.total ? `${visible.total} ${visible.total === 1 ? 'item' : 'itens'}` : 'Nenhum item encontrado.';
  }
  function remember() {
    if (source) states.set(source.id, {query: search.value, limit, selected, scroll: root.scrollTop});
  }
  async function activate(next, {refresh = false} = {}) {
    if (disposed) return;
    remember(); controller?.abort(); controller = new AbortController();
    source = next; items = []; const revision = ++generation;
    const old = states.get(next.id); selected = old?.selected || ''; limit = old?.limit || 80;
    search.value = old?.query || ''; root.replaceChildren(); more.hidden = true;
    status.textContent = 'Carregando…'; root.setAttribute('aria-busy', 'true');
    try {
      const data = await loadItems(next, {refresh, signal: controller.signal});
      if (revision !== generation) return;
      if (!Array.isArray(data) || data.some(item => !item || typeof item.id !== 'string' || typeof item.title !== 'string') || new Set(data.map(item => item.id)).size !== data.length) throw new TypeError('Itens de menu inválidos.');
      items = data; paint(); root.scrollTop = old?.scroll || 0;
    } catch (error) {
      if (revision === generation && error.name !== 'AbortError') status.textContent = error.message;
    } finally { if (revision === generation) root.removeAttribute('aria-busy'); }
  }
  const input = () => { limit = 80; if (source) paint(); };
  const expand = () => { limit += 80; paint(); };
  const click = event => {
    const button = event.target.closest('[data-item]'); if (!button || !root.contains(button)) return;
    const item = items.find(row => row.id === button.dataset.item); if (!item) return;
    selected = item.id; paint(); remember(); onSelect(source, item);
  };
  search.addEventListener('input', input); more.addEventListener('click', expand); root.addEventListener('click', click);
  return {activate, dispose() {
    if (disposed) return;
    disposed = true; ++generation; controller?.abort(); states.clear(); items = []; root.replaceChildren(); root.removeAttribute('aria-busy');
    search.removeEventListener('input', input); more.removeEventListener('click', expand); root.removeEventListener('click', click);
  }};
}
