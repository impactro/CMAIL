/* Presentation only: same-origin tokens, never identity, cookies or theme preferences. */
(() => {
  'use strict';
  if (window.CAFrameTheme) return;
  const root = document.documentElement;
  const names = ['canvas','surface','surface-alt','text','muted','border','action','on-action',
    'focus','success','warning','danger','radius','space','font','hover','selection','info'];
  const attributes = ['style','class','data-ca-theme','data-theme','data-ca-theme-provider'];
  const inherited = new Map(), derived = new Map();
  let owner = null, subscriptions = [], watching = true;

  function put(store, key, value) {
    if (!store.has(key)) store.set(key, {original:root.style.getPropertyValue(key),
      priority:root.style.getPropertyPriority(key), written:''});
    store.get(key).written = value;
    if (root.style.getPropertyValue(key) !== value) root.style.setProperty(key, value);
  }

  function restore(store, key) {
    const previous = store.get(key);
    if (!previous) return;
    if (root.style.getPropertyValue(key) === previous.written) {
      if (previous.original) root.style.setProperty(key, previous.original, previous.priority);
      else root.style.removeProperty(key);
    }
    store.delete(key);
  }

  function restoreAll(store) {
    for (const key of [...store.keys()]) restore(store, key);
  }

  function inspectAncestors() {
    const ancestors = [];
    let candidate = window;
    try {
      while (candidate !== candidate.parent) {
        candidate = candidate.parent;
        const doc = candidate.document, element = doc.documentElement;
        ancestors.push({window:candidate, document:doc, root:element});
        const marker = element.getAttribute('data-ca-theme-provider');
        if (marker === 'ca' || marker === 'cwh') return {ancestors, owner:candidate};
        if (!marker && doc.querySelector('.ca-shell') &&
            candidate.getComputedStyle(element).getPropertyValue('--ca-ui-text').trim()) {
          return {ancestors, owner:candidate};
        }
      }
    } catch { /* Opaque/cross-origin parents are a boundary, not a discovery target. */ }
    return {ancestors, owner:null};
  }

  function disconnect() {
    for (const subscription of subscriptions) {
      subscription.observer.disconnect();
      try {
        subscription.document.removeEventListener('load', refresh, true);
        subscription.document.removeEventListener('ca:theme-change', refresh);
        subscription.window.removeEventListener('ca:theme-change', refresh);
      } catch { /* Parent may have navigated after we subscribed. */ }
    }
    subscriptions = [];
  }

  function observe(ancestors) {
    if (!watching) return;
    if (subscriptions.length === ancestors.length &&
        subscriptions.every((entry, index) => entry.root === ancestors[index].root)) return;
    disconnect();
    for (const ancestor of ancestors) {
      try {
        const observer = new MutationObserver(refresh);
        observer.observe(ancestor.root, {attributes:true, attributeFilter:attributes});
        ancestor.document.addEventListener('load', refresh, true);
        ancestor.document.addEventListener('ca:theme-change', refresh);
        ancestor.window.addEventListener('ca:theme-change', refresh);
        subscriptions.push({...ancestor, observer});
      } catch { /* Do not weaken the frame boundary if a parent becomes inaccessible. */ }
    }
  }

  function actionForeground(action, dark) {
    const fallback = dark ? '#10101a' : '#fff';
    try {
      const ctx = document.createElement('canvas').getContext('2d');
      if (!ctx) return fallback;
      ctx.fillStyle = action || '#343d48';
      ctx.fillRect(0,0,1,1);
      const rgb = [...ctx.getImageData(0,0,1,1).data].slice(0,3).map(value => {
        const channel = value / 255;
        return channel <= .04045 ? channel / 12.92 : ((channel + .055) / 1.055) ** 2.4;
      });
      return rgb[0]*.2126 + rgb[1]*.7152 + rgb[2]*.0722 > .179 ? '#10101a' : '#fff';
    } catch { return fallback; }
  }

  function semantics(source, store) {
    const dark = (source.colorScheme || 'light').split(/\s+/)[0] === 'dark';
    const fallbacks = {'on-action':() => actionForeground(source.getPropertyValue('--ca-ui-action'), dark),
      success:() => dark ? '#85ddb2' : '#226241', warning:() => dark ? '#ffd275' : '#795107'};
    for (const [name, fallback] of Object.entries(fallbacks)) {
      const key = '--ca-ui-' + name, explicit = source.getPropertyValue(key).trim();
      if (store === inherited || !explicit) put(store, key, explicit || fallback());
    }
  }

  function refresh() {
    restoreAll(derived);
    const selection = inspectAncestors();
    observe(selection.ancestors);
    owner = selection.owner;
    if (owner) {
      try {
        const source = owner.getComputedStyle(owner.document.documentElement);
        if (!source.getPropertyValue('--ca-ui-text').trim()) {
          // A declared provider can publish its tokens later; never borrow an outer theme.
          owner = null;
        } else {
          for (const name of names) {
            const key = '--ca-ui-' + name, value = source.getPropertyValue(key).trim();
            if (value) put(inherited, key, value);
            else restore(inherited, key);
          }
          put(inherited, 'color-scheme', source.colorScheme || 'light');
          semantics(source, inherited);
          return true;
        }
      } catch { owner = null; }
    }
    restoreAll(inherited);
    semantics(window.getComputedStyle(root), derived);
    return false;
  }

  function start() { watching = true; refresh(); }
  window.addEventListener('pagehide', () => { watching = false; disconnect(); });
  window.addEventListener('pageshow', start);
  start();
  window.CAFrameTheme = Object.freeze({refresh, inherited:() => Boolean(owner)});
})();
