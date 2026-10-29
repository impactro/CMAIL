(() => {
  'use strict';
  const body = document.body;
  if (body.dataset.authenticated !== 'true') return;

  const base = body.dataset.base || '';
  const csrf = body.dataset.csrf || '';
  const notice = document.querySelector('#notice');
  const foldersNode = document.querySelector('#folders');
  const messagesNode = document.querySelector('#messages');
  const listsNode = document.querySelector('#lists');
  const listSelect = document.querySelector('#listId');
  let folder = 'INBOX';
  let folderName = 'Caixa de entrada';
  let pending = null;
  let selectedMessage = null;
  let composeAction = 'send';
  let composeMessage = null;
  let mailFolders = [], messageItems = [], actions = {};
  let busy = false, readerVersion = 0, listVersion = 0;
  let pendingDelete = null;

  function icon(name) {
    const node = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    for (const [key, value] of Object.entries({class: 'cm-icon', viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': '1.7', 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'aria-hidden': 'true', focusable: 'false'})) node.setAttribute(key, value);
    const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
    use.setAttribute('href', `#cm-icon-${name}`); node.append(use); return node;
  }
  const folderRoles = {
    inbox: ['inbox', 'caixa de entrada', 'entrada'],
    sent: ['sent', 'sentitems', 'sent items', 'sent mail', 'enviados', 'itens enviados'],
    drafts: ['draft', 'drafts', 'rascunhos'],
    archive: ['archive', 'archives', 'arquivo', 'arquivados'],
    trash: ['trash', 'deleteditems', 'deleted items', 'bin', 'lixeira', 'itens excluídos'],
    junk: ['junk', 'junkemail', 'junk e-mail', 'spam', 'lixo eletrônico'],
  };
  const folderLabels = {inbox: 'Caixa de entrada', sent: 'Enviados', drafts: 'Rascunhos', archive: 'Arquivo', trash: 'Lixeira', junk: 'Spam'};
  function folderRole(item) {
    const known = String(item.wellKnownName || '').toLowerCase();
    if (folderLabels[known]) return known;
    const leaf = String(item.name || item.id).split(/[/.]/).pop().trim().toLowerCase();
    return Object.keys(folderRoles).find(role => folderRoles[role].includes(leaf)) || 'folder';
  }
  function folderLabel(item) { return folderLabels[folderRole(item)] || item.name || item.id; }
  function targetFolder(role) { return mailFolders.find(item => folderRole(item) === role && item.id !== folder); }
  function inTrash() { return folderRole(mailFolders.find(item => item.id === folder) || {}) === 'trash'; }
  function updateActions() {
    const selected = Boolean(selectedMessage);
    document.querySelector('#messageActions').hidden = !selected;
    document.querySelector('#selectionHint').hidden = selected;
    document.querySelectorAll('[data-capability]').forEach(node => {
      node.hidden = !actions[node.dataset.capability]; node.disabled = busy;
    });
    document.querySelector('#archiveMessage').hidden = !actions.move || !targetFolder('archive');
    const remove = document.querySelector('#trashMessage');
    remove.hidden = !actions.trash || !mailFolders.some(item => folderRole(item) === 'trash');
    remove.disabled = busy || (inTrash() && !actions.deletePermanently);
    remove.title = inTrash() ? (actions.deletePermanently ? 'Excluir definitivamente' : 'Exclusão definitiva indisponível nesta autorização ou servidor') : 'Excluir — mover para a lixeira';
    document.querySelector('#deleteContext').textContent = remove.title;
    document.querySelector('#moveMessage').disabled = busy || !mailFolders.some(item => item.id !== folder && item.canMoveTo !== false);
    const label = selectedMessage?.isRead ? 'Marcar como não lida' : 'Marcar como lida';
    const read = document.querySelector('#toggleRead');
    read.setAttribute('aria-label', label); read.title = label;
    read.replaceChildren(icon(selectedMessage?.isRead ? 'mail' : 'open-mail'));
    const index = visibleMessages().findIndex(item => item.id === selectedMessage?.id);
    document.querySelector('#previousMessage').disabled = busy || index <= 0;
    document.querySelector('#nextMessage').disabled = busy || index < 0 || index >= visibleMessages().length - 1;
    for (const id of ['execute', 'confirmMove', 'confirmTrash', 'refresh']) document.getElementById(id).disabled = busy;
  }
  function clearSelection() {
    readerVersion++; selectedMessage = null;
    document.querySelector('#readerEmpty').hidden = false;
    document.querySelector('#readerContent').hidden = true;
    updateActions();
  }
  function visibleMessages() {
    const query = document.querySelector('#messageFilter').value.trim().toLocaleLowerCase('pt-BR');
    return messageItems.filter(item => !query || [item.subject, item.from?.name, item.from?.address, item.preview].join(' ').toLocaleLowerCase('pt-BR').includes(query));
  }

  function endpoint(path) { return `${base}${path}`; }
  function setNotice(message, error = false) {
    notice.textContent = message;
    notice.dataset.error = error ? 'true' : 'false';
  }
  async function json(path, options = {}) {
    const response = await fetch(endpoint(path), options);
    let data;
    try { data = await response.json(); } catch (_) { throw new Error('O CMAIL devolveu uma resposta inválida.'); }
    if (!response.ok) throw new Error(data.error || 'Falha na operação.');
    return data;
  }
  function effect(method, value) {
    return { method, headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf}, body: JSON.stringify(value) };
  }
  function button(label, className = '') {
    const value = document.createElement('button');
    value.type = 'button'; value.textContent = label; value.className = className;
    return value;
  }
  function shortDate(raw) {
    const value = new Date(raw);
    return Number.isNaN(value.getTime()) ? '' : new Intl.DateTimeFormat('pt-BR', {day:'2-digit', month:'2-digit', hour:'2-digit', minute:'2-digit'}).format(value);
  }

  async function loadFolders() {
    const data = await json('/api/folders');
    mailFolders = data.folders;
    const selected = mailFolders.find(item => item.id === folder) || mailFolders.find(item => folderRole(item) === 'inbox') || mailFolders[0];
    if (selected) { folder = selected.id; folderName = folderLabel(selected); }
    foldersNode.replaceChildren();
    data.folders.forEach(item => {
      const row = button('', 'cm-folder');
      row.dataset.id = item.id;
      row.title = item.name || item.id;
      const label = document.createElement('span'); label.className = 'cm-folder-label'; label.textContent = folderLabel(item);
      const count = document.createElement('span'); count.className = 'folder-count'; count.textContent = String(item.unread ?? '');
      row.append(icon(folderRole(item)), label, count);
      row.addEventListener('click', () => {
        if (busy) return;
        folder = item.id; folderName = folderLabel(item); document.querySelector('#folderTitle').textContent = folderName;
        document.querySelector('#messageFilter').value = '';
        clearSelection();
        foldersNode.querySelectorAll('button').forEach(node => { node.classList.toggle('active', node === row); if (node === row) node.setAttribute('aria-current', 'page'); else node.removeAttribute('aria-current'); });
        loadMessages().catch(showError);
      });
      foldersNode.append(row);
    });
    const active = [...foldersNode.querySelectorAll('button')].find(node => node.dataset.id === folder) || foldersNode.querySelector('button');
    if (active) { active.classList.add('active'); active.setAttribute('aria-current', 'page'); }
    document.querySelector('#folderTitle').textContent = folderName;
    updateActions();
  }

  async function loadMessages(keepSelection = false) {
    const version = ++listVersion, sourceFolder = folder;
    if (!keepSelection) { clearSelection(); messageItems = []; messagesNode.replaceChildren(); }
    setNotice('Atualizando mensagens…');
    const data = await json(`/api/messages?folder=${encodeURIComponent(sourceFolder)}`);
    if (version !== listVersion || sourceFolder !== folder) return;
    messageItems = data.messages;
    if (selectedMessage && !messageItems.some(item => item.id === selectedMessage.id)) clearSelection();
    renderMessages();
  }
  function renderMessages() {
    messagesNode.replaceChildren();
    const visible = visibleMessages();
    visible.forEach(item => {
      const row = button('', `message-item${item.isRead ? '' : ' unread'}`);
      row.dataset.id = item.id;
      row.classList.toggle('active', item.id === selectedMessage?.id);
      row.setAttribute('aria-pressed', String(item.id === selectedMessage?.id));
      const state = icon(item.isRead ? 'open-mail' : 'mail'); state.classList.add('cm-message-state');
      const sender = document.createElement('span'); sender.className = 'sender'; sender.textContent = item.from?.name || item.from?.address || '(remetente não informado)';
      const date = document.createElement('span'); date.className = 'date'; date.textContent = shortDate(item.receivedAt);
      const subject = document.createElement('span'); subject.className = 'subject'; subject.textContent = item.subject || '(sem assunto)';
      const preview = document.createElement('span'); preview.className = 'preview'; preview.textContent = item.preview || '';
      row.append(state, sender, date, subject, preview);
      if (item.hasAttachments) { const attachment = icon('attachment'); attachment.classList.add('cm-message-attachment'); row.append(attachment); }
      row.addEventListener('click', () => openMessage(item.id, row).catch(showError));
      messagesNode.append(row);
    });
    if (!visible.length) {
      const empty = document.createElement('div'); empty.className = 'cm-list-empty';
      const text = document.createElement('p'); text.textContent = messageItems.length ? 'Nenhuma mensagem corresponde ao filtro.' : 'Nenhuma mensagem nesta pasta.';
      empty.append(icon('inbox'), text); messagesNode.append(empty);
    }
    setNotice(`${visible.length} de ${messageItems.length} mensagem(ns) carregada(s) em ${folderName}.`);
    updateActions();
  }

  async function openMessage(identifier, row) {
    if (busy) return;
    const version = ++readerVersion, sourceFolder = folder;
    selectedMessage = null; updateActions();
    document.querySelector('#readerContent').hidden = true;
    document.querySelector('#readerEmpty').hidden = false;
    setNotice('Abrindo mensagem…');
    const data = await json(`/api/messages/${encodeURIComponent(identifier)}?folder=${encodeURIComponent(sourceFolder)}`);
    if (version !== readerVersion || sourceFolder !== folder) return;
    selectedMessage = data.message;
    document.querySelector('#readerEmpty').hidden = true;
    document.querySelector('#readerContent').hidden = false;
    document.querySelector('#readSubject').textContent = selectedMessage.subject || '(sem assunto)';
    document.querySelector('#readFrom').textContent = selectedMessage.from?.name ? `${selectedMessage.from.name} <${selectedMessage.from.address}>` : (selectedMessage.from?.address || '');
    document.querySelector('#readDate').textContent = shortDate(selectedMessage.receivedAt);
    document.querySelector('#readBody').textContent = selectedMessage.body || '';
    const addresses = values => (values || []).map(item => item.name ? `${item.name} <${item.address}>` : item.address).join(', ');
    document.querySelector('#readRecipients').textContent = [selectedMessage.to?.length ? `Para: ${addresses(selectedMessage.to)}` : '', selectedMessage.cc?.length ? `Cc: ${addresses(selectedMessage.cc)}` : ''].filter(Boolean).join(' · ');
    const attachments = document.querySelector('#readAttachments'); attachments.replaceChildren();
    (selectedMessage.attachments || []).forEach(item => {
      const chip = document.createElement('span'); chip.className = 'cm-attachment';
      const label = document.createElement('span'); label.textContent = item.name || 'Anexo'; chip.append(icon('attachment'), label); attachments.append(chip);
    });
    attachments.hidden = !attachments.childElementCount;
    messagesNode.querySelectorAll('.message-item').forEach(node => { const active = node === row; node.classList.toggle('active', active); node.setAttribute('aria-pressed', String(active)); });
    updateActions();
    setNotice('Mensagem selecionada. As ações estão na barra superior.');
  }

  async function loadLists() {
    const data = await json('/api/lists');
    listsNode.replaceChildren();
    listSelect.replaceChildren(new Option('Nenhuma', ''));
    data.lists.forEach(item => {
      const row = document.createElement('div'); row.className = 'list-row';
      const name = document.createElement('span'); name.textContent = item.name;
      const count = document.createElement('span'); count.textContent = String(item.recipients);
      row.append(name, count); listsNode.append(row);
      listSelect.add(new Option(`${item.name} (${item.recipients})`, String(item.id)));
    });
    if (!data.lists.length) { const empty = document.createElement('p'); empty.textContent = 'Nenhuma lista.'; listsNode.append(empty); }
  }

  function showCompose(options = {}) {
    composeAction = options.action || 'send';
    composeMessage = selectedMessage ? {...selectedMessage, folder} : null;
    document.querySelector('#composePane').hidden = false;
    document.querySelector('#composeTitle').textContent = options.title || 'Nova mensagem';
    document.querySelector('#to').value = options.to || '';
    document.querySelector('#subject').value = options.subject || '';
    document.querySelector('#body').value = options.body || '';
    document.querySelector('#listId').disabled = composeAction !== 'send' || !actions.lists;
    document.querySelector('#subject').readOnly = composeAction !== 'send';
    document.querySelector(composeAction === 'send' ? '#to' : composeAction === 'forward' ? '#to' : '#body').focus();
  }
  function showError(error) { setNotice(error.message || 'Falha inesperada.', true); }

  document.querySelector('#refresh').addEventListener('click', async () => { try { await loadFolders(); await loadMessages(); } catch (error) { showError(error); } });
  document.querySelector('#messageFilter').addEventListener('input', () => { if (selectedMessage && !visibleMessages().some(item => item.id === selectedMessage.id)) clearSelection(); renderMessages(); });
  document.querySelector('#newMessage').addEventListener('click', () => showCompose());
  document.querySelector('#closeCompose').addEventListener('click', () => { document.querySelector('#composePane').hidden = true; composeAction = 'send'; });
  document.querySelector('#showListForm').addEventListener('click', () => { document.querySelector('#listForm').hidden = false; document.querySelector('#listName').focus(); });
  document.querySelector('#cancelList').addEventListener('click', () => { document.querySelector('#listForm').hidden = true; });
  document.querySelector('#listForm').addEventListener('submit', async event => {
    event.preventDefault();
    try {
      const recipients = document.querySelector('#listRecipients').value.split(/\r?\n/).map(address => address.trim()).filter(Boolean).map(address => ({address}));
      await json('/api/lists', effect('POST', {name: document.querySelector('#listName').value, recipients}));
      event.target.reset(); event.target.hidden = true; await loadLists(); setNotice('Lista salva no estado isolado da conta.');
    } catch (error) { showError(error); }
  });
  document.querySelector('#composeForm').addEventListener('submit', async event => {
    event.preventDefault();
    try {
      const recipients = document.querySelector('#to').value.split(';').map(value => value.trim()).filter(Boolean);
      const listId = listSelect.value;
      if (composeAction === 'reply' || composeAction === 'replyAll') {
        pending = {kind: 'reply', id: composeMessage.id, folder: composeMessage.folder, comment: document.querySelector('#body').value, replyAll: composeAction === 'replyAll'};
        document.querySelector('#confirmText').textContent = `${pending.replyAll ? 'Responder a todos' : 'Responder'} esta mensagem?`;
        document.querySelector('#confirm').showModal();
        return;
      }
      if (composeAction === 'forward') {
        pending = {kind: 'forward', id: composeMessage.id, folder: composeMessage.folder, recipients, comment: document.querySelector('#body').value};
        document.querySelector('#confirmText').textContent = `Encaminhar esta mensagem para ${recipients.length} destinatário(s)?${['imap', 'gmail'].includes(body.dataset.mode) ? ' Será encaminhado somente o texto, sem anexos.' : ''}`;
        document.querySelector('#confirm').showModal();
        return;
      }
      const data = await json('/api/send/prepare', effect('POST', {recipients, listId: listId ? Number(listId) : null, subject: document.querySelector('#subject').value, body: document.querySelector('#body').value}));
      pending = {kind: 'send', ...data.preview};
      document.querySelector('#confirmText').textContent = `Enviar “${pending.subject}” para ${pending.recipientCount} destinatário(s)?`;
      document.querySelector('#confirm').showModal();
    } catch (error) { showError(error); }
  });
  document.querySelector('#execute').addEventListener('click', async () => {
    if (busy || !pending) return;
    busy = true; updateActions();
    try {
      let data;
      if (pending.kind === 'reply') {
        data = await json(`/api/messages/${encodeURIComponent(pending.id)}/reply`, effect('POST', {comment: pending.comment, replyAll: pending.replyAll, folder: pending.folder, confirmed: true}));
      } else if (pending.kind === 'forward') {
        data = await json(`/api/messages/${encodeURIComponent(pending.id)}/forward`, effect('POST', {recipients: pending.recipients, comment: pending.comment, folder: pending.folder, confirmed: true}));
      } else {
        data = await json('/api/send/execute', effect('POST', {draftId: pending.draftId, confirmationToken: pending.confirmationToken, confirmed: true}));
      }
      const demo = data.result?.demo === true;
      setNotice(demo ? 'Demonstração concluída: nenhum e-mail foi enviado.' : 'Operação aceita pelo provedor de e-mail.');
      document.querySelector('#confirm').close(); document.querySelector('#composeForm').reset(); document.querySelector('#composePane').hidden = true; composeAction = 'send'; pending = null;
    } catch (error) { pending = null; document.querySelector('#confirm').close(); showError(error); }
    finally { busy = false; updateActions(); }
  });
  document.querySelector('#cancel').addEventListener('click', () => { document.querySelector('#confirm').close(); pending = null; });
  document.querySelector('#toggleRead').addEventListener('click', async () => {
    if (!selectedMessage) return;
    if (busy) return;
    busy = true; updateActions();
    try { const data = await json(`/api/messages/${encodeURIComponent(selectedMessage.id)}/read`, effect('PATCH', {isRead: !selectedMessage.isRead, folder})); selectedMessage.isRead = data.message.isRead; await loadMessages(true); } catch (error) { showError(error); }
    finally { busy = false; updateActions(); }
  });
  document.querySelector('#reply').addEventListener('click', () => selectedMessage && showCompose({action: 'reply', title: 'Responder', to: selectedMessage.from?.address || '', subject: `RE: ${selectedMessage.subject || ''}`}));
  document.querySelector('#replyAll').addEventListener('click', () => selectedMessage && showCompose({action: 'replyAll', title: 'Responder a todos', to: [selectedMessage.from?.address, ...(selectedMessage.to || []).map(item => item.address)].filter(Boolean).join('; '), subject: `RE: ${selectedMessage.subject || ''}`}));
  document.querySelector('#forward').addEventListener('click', () => selectedMessage && showCompose({action: 'forward', title: 'Encaminhar', subject: `ENC: ${selectedMessage.subject || ''}`}));
  document.querySelector('#logout')?.addEventListener('click', async () => { try { await json('/auth/logout', effect('POST', {})); location.reload(); } catch (error) { showError(error); } });

  async function moveSelected(destinationId) {
    if (busy || !selectedMessage) return;
    busy = true; updateActions();
    try {
      await json(`/api/messages/${encodeURIComponent(selectedMessage.id)}/move`, effect('POST', {destinationId, folder}));
      clearSelection(); await loadFolders(); await loadMessages();
      setNotice('Mensagem movida.');
    } finally { busy = false; updateActions(); }
  }
  document.querySelector('#moveMessage').addEventListener('click', () => {
    if (!selectedMessage) return;
    const select = document.querySelector('#destinationFolder'); select.replaceChildren();
    mailFolders.filter(item => item.id !== folder && item.canMoveTo !== false).forEach(item => select.add(new Option(folderLabel(item), item.id)));
    document.querySelector('#moveSubject').textContent = selectedMessage.subject || '(sem assunto)';
    document.querySelector('#moveDialog').showModal(); select.focus();
  });
  document.querySelector('#moveForm').addEventListener('submit', async event => {
    event.preventDefault();
    try { await moveSelected(document.querySelector('#destinationFolder').value); document.querySelector('#moveDialog').close(); }
    catch (error) { document.querySelector('#moveDialog').close(); showError(error); }
  });
  document.querySelector('#cancelMove').addEventListener('click', () => document.querySelector('#moveDialog').close());
  document.querySelector('#archiveMessage').addEventListener('click', () => { const target = targetFolder('archive'); if (target) moveSelected(target.id).catch(showError); });
  async function performDeletion(snapshot) {
    if (busy) return;
    busy = true; updateActions();
    try {
      const action = snapshot.permanent ? 'delete-permanently' : 'trash';
      const payload = snapshot.permanent ? {folder: snapshot.folder, confirmed: true} : {folder: snapshot.folder};
      await json(`/api/messages/${encodeURIComponent(snapshot.id)}/${action}`, effect('POST', payload));
      clearSelection(); await loadFolders(); await loadMessages();
      setNotice(snapshot.permanent ? 'Mensagem excluída definitivamente.' : 'Mensagem movida para a Lixeira.');
      document.querySelector('#trashDialog').close();
    } catch (error) { document.querySelector('#trashDialog').close(); clearSelection(); showError(error); }
    finally { busy = false; updateActions(); }
  }
  document.querySelector('#trashMessage').addEventListener('click', async () => {
    if (!selectedMessage || busy) return;
    const snapshot = {id: selectedMessage.id, folder, permanent: inTrash()};
    if (!snapshot.permanent) { await performDeletion(snapshot); return; }
    pendingDelete = snapshot;
    document.querySelector('#trashSubject').textContent = selectedMessage.subject || '(sem assunto)';
    document.querySelector('#trashDialog').showModal(); document.querySelector('#cancelTrash').focus();
  });
  document.querySelector('#cancelTrash').addEventListener('click', () => { pendingDelete = null; document.querySelector('#trashDialog').close(); });
  document.querySelector('#trashDialog').addEventListener('cancel', () => { pendingDelete = null; });
  document.querySelector('#confirmTrash').addEventListener('click', async () => {
    if (busy || !pendingDelete) return;
    const snapshot = pendingDelete; pendingDelete = null;
    await performDeletion(snapshot);
  });
  for (const [id, direction] of [['previousMessage', -1], ['nextMessage', 1]]) {
    document.getElementById(id).addEventListener('click', () => {
      const visible = visibleMessages(), index = visible.findIndex(item => item.id === selectedMessage?.id);
      const target = visible[index + direction];
      if (target) openMessage(target.id, [...messagesNode.querySelectorAll('.message-item')].find(row => row.dataset.id === target.id)).catch(showError);
    });
  }
  document.querySelector('#messageActions').addEventListener('keydown', event => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    const controls = [...event.currentTarget.querySelectorAll('button')].filter(node => !node.hidden && !node.disabled);
    const index = controls.indexOf(document.activeElement); if (index < 0) return;
    event.preventDefault();
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? controls.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + controls.length) % controls.length;
    controls[next].focus();
  });
  (async () => {
    const data = await json('/api/message-actions'); actions = data.actions;
    document.querySelector('#newMessage').hidden = !actions.send;
    document.querySelector('.sidebar-heading').hidden = !actions.lists;
    document.querySelector('#lists').hidden = !actions.lists;
    document.querySelector('#listId').disabled = !actions.lists;
    await loadFolders(); if (actions.lists) await loadLists(); await loadMessages();
  })().catch(showError);
})();
