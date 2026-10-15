/* Public presentation only. Never reads cookies, identity, APIs or frame content. */
(() => {
  'use strict';
  if (window.CAFrameTheme) return;
  const root = document.documentElement;
  const names = ['canvas','surface','text','muted','border','action','focus','danger','radius','space','font'];
  let owner = null, observer = null;
  try {
    let candidate = window;
    while (candidate !== candidate.parent) {
      candidate = candidate.parent;
      if (candidate.document.querySelector('.ca-shell') && candidate.getComputedStyle(candidate.document.documentElement).getPropertyValue('--ca-ui-text').trim()) { owner = candidate; break; }
    }
  } catch { /* Standalone or inaccessible parent keeps the neutral module theme. */ }
  const put = (name, value) => { if (root.style.getPropertyValue(name) !== value) root.style.setProperty(name, value); };
  function refresh() {
    const source = (owner || window).getComputedStyle((owner || window).document.documentElement);
    if (owner) {
      for (const name of names) { const key = '--ca-ui-' + name, value = source.getPropertyValue(key).trim(); if (value) put(key, value); }
      put('color-scheme', source.colorScheme);
    }
    const dark = source.colorScheme.split(' ')[0] === 'dark';
    put('--ca-ui-success', dark ? '#85ddb2' : '#226241');
    put('--ca-ui-warning', dark ? '#ffd275' : '#795107');
    let foreground = dark ? '#10101a' : '#fff';
    const ctx = document.createElement('canvas').getContext('2d');
    if (ctx) {
      ctx.fillStyle = source.getPropertyValue('--ca-ui-action').trim() || '#343d48'; ctx.fillRect(0,0,1,1);
      const rgb = [...ctx.getImageData(0,0,1,1).data].slice(0,3).map(v => { const c=v/255; return c<=.04045 ? c/12.92 : ((c+.055)/1.055)**2.4; });
      foreground = rgb[0]*.2126 + rgb[1]*.7152 + rgb[2]*.0722 > .179 ? '#10101a' : '#fff';
    }
    put('--ca-ui-on-action', foreground);
  }
  function start() {
    refresh();
    if (owner && !observer) {
      observer = new MutationObserver(refresh);
      observer.observe(owner.document.documentElement, {attributes:true, attributeFilter:['style','class','data-ca-theme']});
      owner.document.addEventListener('load', refresh, true);
    }
  }
  start();
  window.addEventListener('pagehide', () => { observer?.disconnect(); observer=null; owner?.document.removeEventListener('load',refresh,true); });
  window.addEventListener('pageshow', start);
  window.CAFrameTheme = Object.freeze({refresh, inherited:() => Boolean(owner)});
})();
