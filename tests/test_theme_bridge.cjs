const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../cmail/static/cm-theme.js'), 'utf8');

class Events {
  constructor() { this.listeners = new Map(); }
  addEventListener(name, callback) {
    if (!this.listeners.has(name)) this.listeners.set(name, new Set());
    this.listeners.get(name).add(callback);
  }
  removeEventListener(name, callback) { this.listeners.get(name)?.delete(callback); }
  fire(name) { for (const callback of [...(this.listeners.get(name) || [])]) callback({type:name}); }
}

class Style {
  constructor(values={}) { this.values = new Map(Object.entries(values)); }
  getPropertyValue(name) { return this.values.get(name) || ''; }
  getPropertyPriority() { return ''; }
  setProperty(name, value) { this.values.set(name, value); }
  removeProperty(name) { this.values.delete(name); }
}

function frame({marker='', legacy=false, values={}, defaults={}}={}) {
  const win = new Events(), doc = new Events();
  const attributes = new Map(marker ? [['data-ca-theme-provider',marker]] : []);
  const root = {style:new Style(values), getAttribute:name=>attributes.get(name) || null};
  doc.documentElement = root;
  doc.querySelector = selector => legacy && selector === '.ca-shell' ? {} : null;
  doc.createElement = () => ({getContext:()=>null});
  win.document = doc;
  win.parent = win;
  win.getComputedStyle = () => ({
    colorScheme:root.style.getPropertyValue('color-scheme') || defaults['color-scheme'] || 'light',
    getPropertyValue:name=>root.style.getPropertyValue(name) || defaults[name] || '',
  });
  return {win, doc, root, attributes};
}

function install(parent=null, inline={}) {
  const local = frame({values:inline, defaults:{'--ca-ui-text':'#20252b',
    '--ca-ui-focus':'#64748b','--ca-ui-action':'#343d48','color-scheme':'light'}});
  if (parent) local.win.parent = parent.win;
  const observers = new Set();
  class Observer {
    constructor(callback) { this.callback = callback; }
    observe(target, options) { this.target = target; this.options = options; observers.add(this); }
    disconnect() { observers.delete(this); }
  }
  const context = vm.createContext({window:local.win,document:local.doc,MutationObserver:Observer});
  vm.runInContext(source, context);
  return {...local, observers, context, css:name=>local.win.getComputedStyle().getPropertyValue(name),
    notify:target=>{for (const observer of [...observers]) if (observer.target === target) observer.callback();}};
}

test('CWH marker inherits explicit semantic tokens, font and dimensions; private tokens stay private', () => {
  const values = {'--ca-ui-text':'#eeeeee','--ca-ui-success':'#12ab34',
    '--ca-ui-warning':'#abcd12','--ca-ui-on-action':'#fedcba','--ca-ui-font':'Georgia, serif',
    '--ca-ui-radius':'13px','--ca-ui-space':'16px','--ca-ui-selection':'#123123',
    '--ca-ui-info':'#456456','--ca-ui-hover':'#789789','--ca-ui-surface-alt':'#111222',
    '--private-user-id':'do-not-copy','color-scheme':'dark'};
  const host = frame({marker:'cwh',values});
  host.doc.createElement = () => {throw new Error('must not use parent canvas');};
  const child = install(host);
  assert.equal(child.win.CAFrameTheme.inherited(), true);
  for (const [name,value] of Object.entries(values)) {
    if (name !== '--private-user-id') assert.equal(child.root.style.getPropertyValue(name),value,name);
  }
  assert.equal(child.css('--private-user-id'),'');
  assert.deepEqual([...child.observers][0].options.attributeFilter.join(','),
    'style,class,data-ca-theme,data-theme,data-ca-theme-provider');
});

test('nearest CWH wins over outer legacy CA; marker removal and late publication rediscover ownership', () => {
  const ca = frame({legacy:true,values:{'--ca-ui-text':'outer-ca'}});
  const cwh = frame({marker:'cwh',values:{'--ca-ui-text':'inner-cwh'}});
  cwh.win.parent = ca.win;
  const child = install(cwh);
  assert.equal(child.css('--ca-ui-text'),'inner-cwh');
  cwh.attributes.delete('data-ca-theme-provider');
  child.notify(cwh.root);
  assert.equal(child.css('--ca-ui-text'),'outer-ca');
  cwh.attributes.set('data-ca-theme-provider','cwh');
  child.notify(cwh.root);
  assert.equal(child.css('--ca-ui-text'),'inner-cwh');
});

test('declared but unready provider keeps local fallback, then accepts its tokens', () => {
  const outer = frame({legacy:true,values:{'--ca-ui-text':'outer'}});
  const host = frame({marker:'cwh'});
  host.win.parent = outer.win;
  const child = install(host);
  assert.equal(child.win.CAFrameTheme.inherited(),false);
  assert.equal(child.css('--ca-ui-text'),'#20252b');
  host.root.style.setProperty('--ca-ui-text','ready');
  child.notify(host.root);
  assert.equal(child.css('--ca-ui-text'),'ready');
});

test('removed host token clears its stale copy; common event refreshes explicit values', () => {
  const host = frame({marker:'ca',values:{'--ca-ui-text':'host','--ca-ui-focus':'old-focus'}});
  const child = install(host);
  host.root.style.removeProperty('--ca-ui-focus');
  host.root.style.setProperty('--ca-ui-font','monospace');
  host.doc.fire('ca:theme-change');
  assert.equal(child.css('--ca-ui-focus'),'#64748b');
  assert.equal(child.css('--ca-ui-font'),'monospace');
  host.root.style.setProperty('--ca-ui-font','serif');
  host.win.fire('ca:theme-change');
  assert.equal(child.css('--ca-ui-font'),'serif');
});

test('standalone preserves its explicit semantic values and derives missing ones only', () => {
  const child = install(null,{'--ca-ui-on-action':'local-foreground','--ca-ui-success':'local-success'});
  assert.equal(child.win.CAFrameTheme.inherited(),false);
  assert.equal(child.css('--ca-ui-on-action'),'local-foreground');
  assert.equal(child.css('--ca-ui-success'),'local-success');
  assert.equal(child.css('--ca-ui-warning'),'#795107');
  child.win.CAFrameTheme.refresh();
  assert.equal(child.css('--ca-ui-on-action'),'local-foreground');
});

test('opaque boundary does not borrow outer theme and restores local inline values', () => {
  const host = frame({marker:'cwh',values:{'--ca-ui-text':'host'}});
  const child = install(host,{'--ca-ui-text':'original-local'});
  const opaque = {parent:host.win};
  Object.defineProperty(opaque,'document',{get(){throw new Error('cross-origin');}});
  child.win.parent = opaque;
  assert.doesNotThrow(()=>child.win.CAFrameTheme.refresh());
  assert.equal(child.win.CAFrameTheme.inherited(),false);
  assert.equal(child.css('--ca-ui-text'),'original-local');
  assert.equal(child.observers.size,0);
});

test('pagehide cleans subscriptions; pageshow and duplicate script keep one live bridge', () => {
  const host = frame({marker:'cwh',values:{'--ca-ui-text':'host'}});
  const child = install(host);
  const api = child.win.CAFrameTheme;
  assert.equal(child.observers.size,1);
  vm.runInContext(source,child.context);
  assert.equal(child.win.CAFrameTheme,api);
  child.win.fire('pagehide');
  assert.equal(child.observers.size,0);
  assert.equal(host.doc.listeners.get('ca:theme-change').size,0);
  child.win.fire('pageshow');
  assert.equal(child.observers.size,1);
  assert.equal(host.doc.listeners.get('ca:theme-change').size,1);
});
