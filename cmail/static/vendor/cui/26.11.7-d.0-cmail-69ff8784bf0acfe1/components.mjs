// Presentation only. Every mount owns its listeners and accepts an explicit root.
export function element(document, tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = String(text);
  return node;
}

export function button(document, label, {tone = 'secondary', onClick, disabled = false} = {}) {
  const node = element(document, 'button', 'cui-button', label);
  node.type = 'button'; node.dataset.tone = tone; node.disabled = disabled;
  if (onClick) node.addEventListener('click', onClick);
  return node;
}

export function mountTabs({root, tabs, onChange = () => {}}) {
  const document = root.ownerDocument, list = element(document, 'div', 'cui-tabs');
  list.setAttribute('role', 'tablist'); list.setAttribute('aria-label', 'Categorias');
  const prefix = 'cui-tab-' + (++mountTabs.sequence);
  const entries = tabs.map((tab, i) => {
    const node = button(document, tab.label), panel = element(document, 'section', 'cui-tab-panel');
    node.id = `${prefix}-${i}`; panel.id = `${prefix}-panel-${i}`;
    node.setAttribute('role', 'tab'); node.setAttribute('aria-controls', panel.id);
    panel.setAttribute('role', 'tabpanel'); panel.setAttribute('aria-labelledby', node.id);
    panel.tabIndex = 0; panel.append(tab.content); list.append(node); return {node, panel};
  });
  const select = (index, focus = false) => {
    entries.forEach(({node, panel}, i) => {
      node.setAttribute('aria-selected', String(i === index)); node.tabIndex = i === index ? 0 : -1;
      panel.hidden = i !== index;
    });
    if (focus) entries[index].node.focus(); onChange(tabs[index].id);
  };
  const click = event => { const i = entries.findIndex(x => x.node.contains(event.target)); if (i >= 0) select(i); };
  const key = event => {
    const i = entries.findIndex(x => x.node === event.target);
    if (i < 0 || !['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    select(event.key === 'Home' ? 0 : event.key === 'End' ? entries.length - 1 : (i + (event.key === 'ArrowRight' ? 1 : -1) + entries.length) % entries.length, true);
  };
  list.addEventListener('click', click); list.addEventListener('keydown', key);
  root.replaceChildren(list, ...entries.map(x => x.panel)); if (entries.length) select(0);
  return {dispose() { list.removeEventListener('click', click); list.removeEventListener('keydown', key); root.replaceChildren(); }};
}
mountTabs.sequence = 0;

export function mountDialog({root, title, content, actions = [{id: 'cancel', label: 'Fechar'}]}) {
  const document = root.ownerDocument, dialog = element(document, 'dialog', 'cui-dialog');
  const heading = element(document, 'h2', 'cui-dialog-title', title);
  heading.id = 'cui-dialog-' + (++mountDialog.sequence); dialog.setAttribute('aria-labelledby', heading.id);
  const body = element(document, 'div', 'cui-dialog-body'); body.append(content);
  const footer = element(document, 'div', 'cui-actions');
  const controls = actions.map(action => {const node = button(document, action.label, {tone: action.tone}); node.dataset.action = action.id; footer.append(node); return node;});
  dialog.append(heading, body, footer); root.append(dialog);
  let resolve, trigger, disposed = false;
  const finish = result => {
    if (!resolve) return;
    if (dialog.open && dialog.close) dialog.close(); else dialog.removeAttribute('open');
    const done = resolve; resolve = undefined; trigger?.isConnected && trigger.focus(); done(result);
  };
  const click = event => {const i = controls.findIndex(node => node.contains(event.target)); if (i >= 0) finish(actions[i].id);};
  const cancel = event => {event.preventDefault(); finish('cancel');};
  const close = () => finish('cancel');
  dialog.addEventListener('click', click); dialog.addEventListener('cancel', cancel); dialog.addEventListener('close', close);
  return {element: dialog, show() {
    if (disposed || resolve) throw Error('Diálogo indisponível.');
    trigger = document.activeElement;
    const result = new Promise(done => resolve = done);
    if (dialog.showModal) dialog.showModal(); else dialog.setAttribute('open', '');
    controls[0]?.focus(); return result;
  }, dispose() {if (disposed) return; disposed = true; finish('cancel'); dialog.removeEventListener('click', click); dialog.removeEventListener('cancel', cancel); dialog.removeEventListener('close', close); dialog.remove();}};
}
mountDialog.sequence = 0;

export function mountToast({root}) {
  const node = element(root.ownerDocument, 'div', 'cui-toast'); node.setAttribute('role', 'status'); node.hidden = true; root.append(node);
  let timer, disposed = false;
  return {show(text) {if (disposed) return; clearTimeout(timer); node.textContent = text; node.hidden = false; timer = setTimeout(() => node.hidden = true, 4000);},
    dispose() {disposed = true; clearTimeout(timer); node.remove();}};
}

export function mountPopover({root, trigger, content}) {
  const node = element(root.ownerDocument, 'div', 'cui-popover'); node.append(content); node.hidden = true;
  node.id = 'cui-popover-' + (++mountPopover.sequence); trigger.setAttribute('aria-controls', node.id); trigger.setAttribute('aria-expanded', 'false'); root.append(node);
  const close = () => {node.hidden = true; trigger.setAttribute('aria-expanded', 'false');};
  const click = () => {node.hidden = !node.hidden; trigger.setAttribute('aria-expanded', String(!node.hidden));};
  const outside = event => {if (!node.contains(event.target) && !trigger.contains(event.target)) close();};
  const key = event => {if (event.key === 'Escape' && !node.hidden) {close(); trigger.focus();}};
  trigger.addEventListener('click', click); root.ownerDocument.addEventListener('click', outside); root.ownerDocument.addEventListener('keydown', key);
  return {dispose() {trigger.removeEventListener('click', click); root.ownerDocument.removeEventListener('click', outside); root.ownerDocument.removeEventListener('keydown', key); trigger.removeAttribute('aria-controls'); trigger.removeAttribute('aria-expanded'); node.remove();}};
}
mountPopover.sequence = 0;

export function mountTable({root, columns, rows, pageSize = 5}) {
  const doc = root.ownerDocument, searchLabel = element(doc, 'label', 'cui-field', 'Filtrar tabela');
  const input = element(doc, 'input', 'cui-input'); input.type = 'search'; searchLabel.append(input);
  const viewport = element(doc, 'div', 'cui-table-viewport'), table = element(doc, 'table', 'cui-table');
  const caption = element(doc, 'caption', '', 'Registros fictícios'), head = doc.createElement('thead'), header = doc.createElement('tr'), body = doc.createElement('tbody');
  let page = 0, order = null, ascending = true, disposed = false;
  const normalize = text => String(text).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('pt-BR');
  const selected = () => {
    const query = normalize(input.value), filtered = rows.filter(row => columns.some(col => normalize(row[col.key] ?? '').includes(query)));
    return order ? filtered.sort((a, b) => String(a[order] ?? '').localeCompare(String(b[order] ?? ''), 'pt-BR', {numeric: true}) * (ascending ? 1 : -1)) : filtered;
  };
  const sorts = [];
  columns.forEach(col => {const th = doc.createElement('th'); th.scope = 'col'; const node = button(doc, col.label + ' ↕'); const click = () => {ascending = order === col.key ? !ascending : true; order = col.key; page = 0; paint();}; node.addEventListener('click', click); sorts.push({node, click, th, key: col.key}); th.append(node); header.append(th);});
  head.append(header); table.append(caption, head, body); viewport.append(table);
  const footer = element(doc, 'div', 'cui-pagination'), status = element(doc, 'span', 'cui-table-status'); status.setAttribute('role', 'status');
  const previous = button(doc, '← Anterior'), next = button(doc, 'Próxima →'); footer.append(previous, status, next);
  function paint() {
    if (disposed) return;
    const data = selected(), pages = Math.max(1, Math.ceil(data.length / pageSize)); page = Math.min(page, pages - 1); body.replaceChildren();
    for (const row of data.slice(page * pageSize, (page + 1) * pageSize)) {const tr = doc.createElement('tr'); for (const col of columns) tr.append(element(doc, 'td', '', row[col.key] ?? '—')); body.append(tr);}
    if (!data.length) {const tr = doc.createElement('tr'), td = element(doc, 'td', 'cui-empty', 'Nenhum registro encontrado.'); td.colSpan = columns.length; tr.append(td); body.append(tr);}
    status.textContent = `Página ${page + 1} de ${pages} · ${data.length} registros`; previous.disabled = page === 0; next.disabled = page + 1 >= pages;
    for (const item of sorts) item.th.setAttribute('aria-sort', order === item.key ? (ascending ? 'ascending' : 'descending') : 'none');
  }
  const filter = () => {page = 0; paint();}, back = () => {page--; paint();}, forward = () => {page++; paint();};
  input.addEventListener('input', filter); previous.addEventListener('click', back); next.addEventListener('click', forward);
  root.replaceChildren(searchLabel, viewport, footer); paint();
  return {dispose() {disposed = true; input.removeEventListener('input', filter); previous.removeEventListener('click', back); next.removeEventListener('click', forward); for (const {node, click} of sorts) node.removeEventListener('click', click); root.replaceChildren();}};
}

export function mountForm({root, onSubmit = () => {}}) {
  const doc = root.ownerDocument, form = element(doc, 'form', 'cui-form'); form.noValidate = true;
  const summary = element(doc, 'p', 'cui-message'); summary.dataset.tone = 'danger'; summary.hidden = true; summary.tabIndex = -1; summary.setAttribute('role', 'alert');
  const fields = [['Nome', 'text'], ['E-mail', 'email'], ['Data', 'date']].map(([label, type], i) => {
    const field = element(doc, 'label', 'cui-field', label), input = element(doc, 'input', 'cui-input'); input.name = ['name', 'email', 'date'][i]; input.type = type; input.required = i < 2;
    const error = element(doc, 'span', 'cui-field-error', 'Revise este campo.'); error.id = `cui-field-${++mountForm.sequence}`; error.hidden = true;
    input.setAttribute('aria-describedby', error.id); field.append(input, error); form.append(field); return {input, error};
  });
  const areaLabel = element(doc, 'label', 'cui-field', 'Observação'), area = element(doc, 'textarea', 'cui-input'); areaLabel.append(area); form.append(areaLabel);
  const choiceLabel = element(doc, 'label', 'cui-field', 'Categoria'), choice = element(doc, 'select', 'cui-input'); for (const label of ['Serviços', 'Indústria', 'Comércio']) choice.append(element(doc, 'option', '', label)); choiceLabel.append(choice); form.append(choiceLabel);
  const options = element(doc, 'fieldset', 'cui-options'); options.append(element(doc, 'legend', '', 'Preferências'));
  for (const [type, label] of [['checkbox', 'Receber resumo'], ['radio', 'Pessoa'], ['radio', 'Empresa']]) {const line = element(doc, 'label', 'cui-inline'); const input = doc.createElement('input'); input.type = type; if (type === 'radio') input.name = 'kind'; line.append(input, doc.createTextNode(label)); options.append(line);} form.append(options);
  const toggleLabel = element(doc, 'label', 'cui-inline', 'Notificações '), toggle = doc.createElement('input'); toggle.type = 'checkbox'; toggle.setAttribute('role', 'switch'); toggleLabel.append(toggle); options.append(toggleLabel);
  const locked = element(doc, 'label', 'cui-field', 'Somente leitura'), value = element(doc, 'input', 'cui-input'); value.readOnly = true; value.value = 'Demonstração'; locked.append(value); form.append(locked);
  const disabled = element(doc, 'input', 'cui-input'); disabled.disabled = true; disabled.placeholder = 'Indisponível'; disabled.setAttribute('aria-label', 'Campo indisponível'); form.append(disabled);
  const save = button(doc, 'Validar exemplo', {tone: 'primary'}); save.type = 'submit'; const reset = button(doc, 'Restaurar'); reset.type = 'reset';
  const submit = event => {event.preventDefault(); let first; for (const {input, error} of fields) {const valid = input.checkValidity() && (!input.required || input.value.trim()); error.hidden = Boolean(valid); input.setAttribute('aria-invalid', String(!valid)); if (!valid && !first) first = input;} summary.hidden = !first; summary.textContent = first ? 'Revise os campos indicados.' : ''; if (first) first.focus(); else onSubmit();};
  const restore = () => {summary.hidden = true; for (const {input, error} of fields) {input.removeAttribute('aria-invalid'); error.hidden = true;}};
  form.prepend(summary); const actions = element(doc, 'div', 'cui-actions'); actions.append(save, reset); form.append(actions); root.replaceChildren(form);
  form.addEventListener('submit', submit); form.addEventListener('reset', restore);
  return {dispose() {form.removeEventListener('submit', submit); form.removeEventListener('reset', restore); root.replaceChildren();}};
}
mountForm.sequence = 0;
