(() => {
  'use strict';
  if (document.body.dataset.authenticated !== 'true') return;
  const base = document.body.dataset.base || '';
  const dialog = document.querySelector('#appearanceDialog');
  const errorNode = document.querySelector('#appearanceError');
  const fieldNodes = [...dialog.querySelectorAll('[data-appearance-field]')];
  let original = {}, assets = [], settings = null, busy = false;
  async function request(path, method = 'GET', payload) {
    const response = await fetch(base + path, {method, credentials:'same-origin',
      headers:{'Content-Type':'application/json','X-CSRF-Token':document.body.dataset.csrf || ''},
      ...(payload === undefined ? {} : {body:JSON.stringify(payload)})});
    const value = await response.json();
    if (!response.ok) throw new Error(value.error || 'Não foi possível configurar a aparência.');
    return value;
  }
  const fail = error => { errorNode.textContent = error.message || String(error); };
  function drawAssets() {
    const parent = document.querySelector('#appearanceAssets'); parent.replaceChildren();
    assets.forEach((item, index) => {
      const row = document.createElement('div'); row.className = 'cm-asset-row';
      const label = document.createElement('span'); label.textContent = item.name || item.file || 'Imagem';
      const identifier = document.createElement('input'); identifier.value = item.contentId;
      identifier.setAttribute('aria-label','Identificador CID de ' + label.textContent);
      identifier.addEventListener('input', () => { item.contentId = identifier.value; });
      const remove = document.createElement('button'); remove.type = 'button'; remove.className = 'quiet-button'; remove.textContent = 'Remover';
      remove.addEventListener('click', () => { assets.splice(index,1); drawAssets(); });
      row.append(label, identifier, remove); parent.append(row);
    });
  }
  function fill(profile) {
    original = structuredClone(profile); assets = structuredClone(profile.assets || []);
    for (const kind of ['new','reply','forward']) for (const slot of ['template','signature']) {
      document.querySelector(`#appearance-${kind}-${slot}`).value = profile.modes?.[kind]?.[slot] || 'inherit';
    }
    fieldNodes.forEach(node => { node.value = profile.fields?.[node.dataset.appearanceField] || ''; });
    const known = new Set(fieldNodes.map(node => node.dataset.appearanceField));
    document.querySelector('#appearanceExtraFields').value = JSON.stringify(Object.fromEntries(Object.entries(profile.fields || {}).filter(([key]) => !known.has(key))), null, 2);
    document.querySelector('#appearanceTemplateHtml').value = profile.templateHtml || '';
    document.querySelector('#appearanceSignatureHtml').value = profile.signatureHtml || '';
    drawAssets(); errorNode.textContent = ''; document.querySelector('#appearancePreview').hidden = true;
  }
  function collect() {
    const fields = JSON.parse(document.querySelector('#appearanceExtraFields').value || '{}');
    if (!fields || Array.isArray(fields) || typeof fields !== 'object') throw new Error('Os campos adicionais devem ser um objeto JSON.');
    fieldNodes.forEach(node => { if (node.value.trim()) fields[node.dataset.appearanceField] = node.value.trim(); });
    const profile = {schemaVersion:'1.0', fields, modes:{}, assets};
    for (const kind of ['new','reply','forward']) {
      profile.modes[kind] = {};
      for (const slot of ['template','signature']) profile.modes[kind][slot] = document.querySelector(`#appearance-${kind}-${slot}`).value;
    }
    for (const slot of ['template','signature']) {
      const source = document.querySelector(slot === 'template' ? '#appearanceTemplateHtml' : '#appearanceSignatureHtml').value;
      if (source.trim()) profile[slot + 'Html'] = source;
      else if (original[slot + 'File']) profile[slot + 'File'] = original[slot + 'File'];
      else if (['new','reply','forward'].some(kind => profile.modes[kind][slot] === 'custom')) profile[slot + 'Html'] = settings[slot === 'template' ? 'defaultTemplateHtml' : 'defaultSignatureHtml'];
    }
    return profile;
  }
  async function locked(action) {
    if (busy) return;
    busy = true; errorNode.textContent = '';
    for (const id of ['saveAppearance','previewAppearance','resetAppearance']) document.getElementById(id).disabled = true;
    try { await action(); } catch(error) { fail(error); }
    finally { busy = false; for (const id of ['saveAppearance','previewAppearance','resetAppearance']) document.getElementById(id).disabled = false; }
  }
  document.querySelector('#configureAppearance').addEventListener('click', () => locked(async () => {
    settings = await request('/api/appearance'); fill(settings.profile);
    const origins = {system:'CMAIL',company:'empresa',personal:'pessoal'};
    document.querySelector('#appearanceOrigin').textContent = `Novas mensagens: template ${origins[settings.effective.new.template.source]}, assinatura ${origins[settings.effective.new.signature.source]}.`;
    document.querySelector('#appearanceFiles').textContent = `Arquivos pessoais: ${settings.workspaceDirectory}. Use profile.json e caminhos relativos para HTML e imagens.`;
    dialog.showModal();
  }).catch(fail));
  document.querySelector('#closeAppearance').addEventListener('click', () => { if (!busy) dialog.close(); });
  document.querySelector('#resetAppearance').addEventListener('click', () => { fill({}); errorNode.textContent = 'Herança restaurada na edição. Salve para aplicar.'; });
  document.querySelector('#appearanceForm').addEventListener('submit', event => { event.preventDefault(); locked(async () => {
    settings = await request('/api/appearance','PUT',collect()); dialog.close();
    document.querySelector('#notice').textContent = 'Template e assinatura salvos. Novas prévias usarão suas preferências.';
  }); });
  document.querySelector('#previewAppearance').addEventListener('click', () => locked(async () => {
    const data = await request('/api/appearance/preview','POST',{profile:collect(),subject:'Prévia da sua mensagem',body:'Olá!\n\nEste é um exemplo do conteúdo do e-mail.\nSua assinatura aparece abaixo.',kind:'new'});
    const frame = document.querySelector('#appearancePreview'); frame.src = data.previewUrl; frame.hidden = false;
  }));
  for (const slot of ['Template','Signature']) document.querySelector(`#import${slot}Html`).addEventListener('change', event => locked(async () => {
    const file = event.target.files[0]; if (!file) return;
    if (file.size > 800000) throw new Error('O arquivo HTML excede o limite.');
    document.querySelector(`#appearance${slot}Html`).value = (await file.text()).replace(/^\uFEFF/,'');
    event.target.value = '';
  }));
  document.querySelector('#appearanceLogo').addEventListener('change', event => locked(async () => {
    const file = event.target.files[0]; if (!file) return;
    if (!['image/png','image/jpeg'].includes(file.type) || file.size > 2097152) throw new Error('Use um logo PNG/JPEG de até dois MiB.');
    const data = await new Promise((resolve,reject) => { const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.onerror = reject; reader.readAsDataURL(file); });
    assets = assets.filter(item => item.contentId !== 'logo');
    assets.push({name:file.name,contentId:'logo',contentType:file.type,contentBase64:data.split(',')[1]});
    drawAssets(); event.target.value = '';
  }));
  document.querySelector('#appearanceImages').addEventListener('change', event => locked(async () => {
    const incoming = [...event.target.files];
    if (assets.length + incoming.length > 8 || incoming.reduce((sum,file) => sum + file.size,0) > 2097152) throw new Error('Use até oito imagens e dois MiB no total.');
    const added = [];
    for (const file of incoming) {
      if (!['image/png','image/jpeg'].includes(file.type)) throw new Error('Use PNG ou JPEG.');
      const data = await new Promise((resolve,reject) => { const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.onerror = reject; reader.readAsDataURL(file); });
      added.push({name:file.name,contentId:file.name.replace(/\.[^.]+$/,'').replace(/[^A-Za-z0-9_.-]/g,'-'),contentType:file.type,contentBase64:data.split(',')[1]});
    }
    assets.push(...added); drawAssets(); event.target.value = '';
  }));
})();
