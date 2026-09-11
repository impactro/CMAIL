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
    foldersNode.replaceChildren();
    data.folders.forEach((item, index) => {
      const row = button(item.name || 'Pasta');
      row.dataset.id = item.id;
      if (index === 0 || item.wellKnownName === 'inbox' || item.id === folder) {
        if (item.wellKnownName === 'inbox' || folder === 'INBOX') { folder = item.id; folderName = item.name; }
      }
      const count = document.createElement('span'); count.className = 'folder-count'; count.textContent = String(item.unread ?? '');
      row.append(count);
      row.addEventListener('click', () => {
        folder = item.id; folderName = item.name; document.querySelector('#folderTitle').textContent = folderName;
        foldersNode.querySelectorAll('button').forEach(node => node.classList.toggle('active', node === row));
        loadMessages().catch(showError);
      });
      foldersNode.append(row);
    });
    const active = [...foldersNode.querySelectorAll('button')].find(node => node.dataset.id === folder) || foldersNode.querySelector('button');
    if (active) active.classList.add('active');
    document.querySelector('#folderTitle').textContent = folderName;
  }

  async function loadMessages() {
    setNotice('Atualizando mensagens…');
    const data = await json(`/api/messages?folder=${encodeURIComponent(folder)}`);
    messagesNode.replaceChildren();
    data.messages.forEach(item => {
      const row = button('', `message-item${item.isRead ? '' : ' unread'}`);
      const sender = document.createElement('span'); sender.className = 'sender'; sender.textContent = item.from?.name || item.from?.address || '(remetente não informado)';
      const date = document.createElement('span'); date.className = 'date'; date.textContent = shortDate(item.receivedAt);
      const subject = document.createElement('span'); subject.className = 'subject'; subject.textContent = item.subject || '(sem assunto)';
      const preview = document.createElement('span'); preview.className = 'preview'; preview.textContent = item.preview || '';
      row.append(sender, date, subject, preview);
      row.addEventListener('click', () => openMessage(item.id, row).catch(showError));
      messagesNode.append(row);
    });
    setNotice(data.messages.length ? `${data.messages.length} mensagem(ns) em ${folderName}.` : 'Nenhuma mensagem nesta pasta.');
  }

  async function openMessage(identifier, row) {
    setNotice('Abrindo mensagem…');
    const data = await json(`/api/messages/${encodeURIComponent(identifier)}?folder=${encodeURIComponent(folder)}`);
    selectedMessage = data.message;
    document.querySelector('#readerEmpty').hidden = true;
    document.querySelector('#readerContent').hidden = false;
    document.querySelector('#readSubject').textContent = selectedMessage.subject || '(sem assunto)';
    document.querySelector('#readFrom').textContent = selectedMessage.from?.name ? `${selectedMessage.from.name} <${selectedMessage.from.address}>` : (selectedMessage.from?.address || '');
    document.querySelector('#readDate').textContent = shortDate(selectedMessage.receivedAt);
    document.querySelector('#readBody').textContent = selectedMessage.body || '';
    document.querySelector('#toggleRead').textContent = selectedMessage.isRead ? 'Marcar como não lida' : 'Marcar como lida';
    messagesNode.querySelectorAll('.message-item').forEach(node => node.classList.toggle('active', node === row));
    setNotice('Mensagem aberta com conteúdo em texto seguro.');
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
    document.querySelector('#composePane').hidden = false;
    document.querySelector('#composeTitle').textContent = options.title || 'Nova mensagem';
    document.querySelector('#to').value = options.to || '';
    document.querySelector('#subject').value = options.subject || '';
    document.querySelector('#body').value = options.body || '';
    document.querySelector('#listId').disabled = composeAction !== 'send';
    document.querySelector('#subject').readOnly = composeAction !== 'send';
    document.querySelector('#subject').focus();
  }
  function showError(error) { setNotice(error.message || 'Falha inesperada.', true); }

  document.querySelector('#refresh').addEventListener('click', () => Promise.all([loadFolders(), loadMessages()]).catch(showError));
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
        pending = {kind: 'reply', id: selectedMessage.id, comment: document.querySelector('#body').value, replyAll: composeAction === 'replyAll'};
        document.querySelector('#confirmText').textContent = `${pending.replyAll ? 'Responder a todos' : 'Responder'} esta mensagem?`;
        document.querySelector('#confirm').showModal();
        return;
      }
      if (composeAction === 'forward') {
        pending = {kind: 'forward', id: selectedMessage.id, recipients, comment: document.querySelector('#body').value};
        document.querySelector('#confirmText').textContent = `Encaminhar esta mensagem para ${recipients.length} destinatário(s)?`;
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
    try {
      let data;
      if (pending.kind === 'reply') {
        data = await json(`/api/messages/${encodeURIComponent(pending.id)}/reply`, effect('POST', {comment: pending.comment, replyAll: pending.replyAll, confirmed: true}));
      } else if (pending.kind === 'forward') {
        data = await json(`/api/messages/${encodeURIComponent(pending.id)}/forward`, effect('POST', {recipients: pending.recipients, comment: pending.comment, confirmed: true}));
      } else {
        data = await json('/api/send/execute', effect('POST', {draftId: pending.draftId, confirmationToken: pending.confirmationToken, confirmed: true}));
      }
      const demo = data.result?.demo === true;
      setNotice(demo ? 'Demonstração concluída: nenhum e-mail foi enviado.' : 'Operação aceita pela Microsoft.');
      document.querySelector('#confirm').close(); document.querySelector('#composeForm').reset(); document.querySelector('#composePane').hidden = true; composeAction = 'send'; pending = null;
    } catch (error) { document.querySelector('#confirm').close(); showError(error); }
  });
  document.querySelector('#cancel').addEventListener('click', () => { document.querySelector('#confirm').close(); pending = null; });
  document.querySelector('#toggleRead').addEventListener('click', async () => {
    if (!selectedMessage) return;
    try { const data = await json(`/api/messages/${encodeURIComponent(selectedMessage.id)}/read`, effect('PATCH', {isRead: !selectedMessage.isRead})); selectedMessage.isRead = data.message.isRead; document.querySelector('#toggleRead').textContent = selectedMessage.isRead ? 'Marcar como não lida' : 'Marcar como lida'; await loadMessages(); } catch (error) { showError(error); }
  });
  document.querySelector('#reply').addEventListener('click', () => selectedMessage && showCompose({action: 'reply', title: 'Responder', to: selectedMessage.from?.address || '', subject: `RE: ${selectedMessage.subject || ''}`}));
  document.querySelector('#replyAll').addEventListener('click', () => selectedMessage && showCompose({action: 'replyAll', title: 'Responder a todos', to: [selectedMessage.from?.address, ...(selectedMessage.to || []).map(item => item.address)].filter(Boolean).join('; '), subject: `RE: ${selectedMessage.subject || ''}`}));
  document.querySelector('#forward').addEventListener('click', () => selectedMessage && showCompose({action: 'forward', title: 'Encaminhar', subject: `ENC: ${selectedMessage.subject || ''}`}));
  document.querySelector('#logout')?.addEventListener('click', async () => { try { await json('/auth/logout', effect('POST', {})); location.reload(); } catch (error) { showError(error); } });

  Promise.all([loadFolders(), loadLists()]).then(loadMessages).catch(showError);
})();
