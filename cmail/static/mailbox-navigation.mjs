import {renderMailRows} from './cui-navigation.mjs';
/* One mailbox list for CMAIL, CAW and CWH. Identity and effects stay on the server. */
export function mountMailboxNavigation(root,{basePath='',initialFolder='',onMessage=()=>{},onCompose=()=>{},onFolders=()=>{}}={}){
  if(!document.querySelector('link[data-cmail-navigation]')){const link=document.createElement('link');link.rel='stylesheet';link.href=new URL('./mailbox-navigation.css',import.meta.url).href;link.dataset.cmailNavigation='true';document.head.append(link)}
  let active=true,folder=initialFolder,query='',selected='',generation=0,controller,timer;
  const make=(tag,text='',cls='')=>{const el=document.createElement(tag);el.textContent=text;if(cls)el.className=cls;return el};
  function button(label,path){const el=make('button');el.type='button';el.title=label;el.setAttribute('aria-label',label);el.innerHTML=`<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${path}"/></svg>`;return el}
  const controls=make('div','','cmail-navigation-controls'),folders=make('select'),search=make('input'),status=make('p'),list=make('nav');
  folders.setAttribute('aria-label','Pasta de e-mail');search.type='search';search.placeholder='Assunto, conteúdo ou destinatário';search.setAttribute('aria-label','Buscar e-mails');search.hidden=true;
  const toggle=button('Buscar e-mails','M21 21l-5-5M10 3a7 7 0 1 0 0 14 7 7 0 0 0 0-14'),compose=button('Novo e-mail','M14 4l6 6M3 21l5-1L21 7l-5-5L3 15z'),refresh=button('Atualizar e-mails','M20 7v5h-5M20 12a8 8 0 1 0-2 5M20 7l-3-3');
  status.setAttribute('role','status');list.setAttribute('aria-label','Lista de e-mails');controls.append(folders,search,toggle,compose,refresh);root.replaceChildren(controls,status,list);root.classList.add('cmail-mailbox-navigation');
  async function json(path,signal){const r=await fetch(basePath+'/api/'+path,{credentials:'same-origin',cache:'no-store',signal});const data=await r.json();if(!r.ok||data.ok===false)throw Error(data.message||data.error?.message||(typeof data.error==='string'?data.error:'Falha ao consultar e-mail.'));return data}
  function date(value){const d=new Date(value),now=new Date();if(!value||!Number.isFinite(d.getTime()))return '';const today=d.toDateString()===now.toDateString();return new Intl.DateTimeFormat('pt-BR',today?{hour:'2-digit',minute:'2-digit'}:{day:'2-digit',month:'2-digit',...(d.getFullYear()!==now.getFullYear()?{year:'numeric'}:{})}).format(d)}
  function fail(error,retry){if(error.name==='AbortError')return;const reported=window.CMHostMessages?.showError(error.message,{operation:'mailbox_query',errorType:error.name||'Error'});status.replaceChildren(...(reported?[]:[make('span',error.message)]));const b=make('button','Tentar novamente');b.type='button';b.onclick=retry;status.append(b)}
  async function reload(){
    if(!active||!folder)return;controller?.abort();controller=new AbortController();const version=++generation,sourceFolder=folder,term=query;status.textContent='Carregando e-mails…';list.setAttribute('aria-busy','true');
    try{
      const data=await json('messages?'+new URLSearchParams({folder:sourceFolder,limit:25,...(term?{q:term}:{})}),controller.signal);
      if(!active||version!==generation)return;list.replaceChildren();
      renderMailRows(list,data.messages,{selected,date,onSelect:(item,row)=>{selected=item.id;for(const r of list.children)r.setAttribute('aria-current',r===row?'page':'false');onMessage({folder:sourceFolder,id:item.id})}});
      status.textContent=data.messages.length?`${data.messages.length} e-mails · mais recentes primeiro${data.search?.fuzzyWindow?' · aproximações no recorte recente':''}`:'Nenhum e-mail encontrado.';
    }catch(error){if(active&&version===generation)fail(error,reload)}finally{if(version===generation)list.removeAttribute('aria-busy')}
  }
  async function load(){
    controller?.abort();controller=new AbortController();const version=++generation;status.textContent='Carregando pastas…';
    try{const data=await json('folders',controller.signal);if(!active||version!==generation)return;folders.replaceChildren();for(const f of data.folders)folders.append(new Option(f.name||f.id,f.id));if(!data.folders.some(f=>f.id===folder))folder=(data.folders.find(f=>f.wellKnownName==='inbox')||data.folders[0])?.id||'';folders.value=folder;onFolders(data.folders);if(folder)await reload();else status.textContent='Nenhuma pasta disponível.';}
    catch(error){if(active&&version===generation)fail(error,load)}
    try{const data=await json('message-actions');if(active)compose.disabled=data.actions?.send!==true}catch{compose.disabled=true}
  }
  compose.disabled=true;compose.onclick=onCompose;refresh.onclick=()=>folder?reload():load();folders.onchange=()=>{folder=folders.value;selected='';void reload()};
  toggle.onclick=()=>{const show=search.hidden;search.hidden=!show;folders.hidden=show;toggle.setAttribute('aria-pressed',String(show));if(show)search.focus();else{clearTimeout(timer);search.value='';query='';void reload()}};
  search.oninput=()=>{clearTimeout(timer);controller?.abort();generation++;query=search.value.trim();status.textContent='Buscando…';timer=setTimeout(reload,350)};
  search.onkeydown=event=>{if(event.key==='Enter'){clearTimeout(timer);void reload()}if(event.key==='Escape')toggle.click()};
  void load();return {reload,load,get folder(){return folder},get query(){return query},dispose(){active=false;clearTimeout(timer);controller?.abort();generation++;root.replaceChildren()}};
}
