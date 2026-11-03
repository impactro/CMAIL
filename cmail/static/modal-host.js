/* Presentation-only adapter: nearest declared host, native local dialog otherwise. */
(() => {
  'use strict';
  function enhance(dialog,options={}) {
    if(!dialog)return false;
    let parent=window;
    try {
      while(parent!==parent.parent){
        parent=parent.parent;
        const marker=parent.document.documentElement.dataset.caThemeProvider;
        if(!['ca','cwh'].includes(marker))continue;
        const provider=parent.CAModal;
        if(provider?.contract!=='ca.modal.v1'||typeof provider.forDocument!=='function')break;
        provider.forDocument(document).enhance(dialog,options);
        dialog.dataset.modalProvider='host';return true;
      }
    } catch {/* Cross-origin/opaque parents keep the local fallback; no postMessage bridge. */}
    dialog.dataset.modalProvider='local';return false;
  }
  window.CMHostModal=Object.freeze({contract:'ca.modal.v1',enhance});

  function messages(){
    let parent=window;
    try{while(true){
      const provider=parent.CAAppMessages;
      if(provider?.contract==='ca.messages.v1')return provider.forDocument(document,{component:'cmail'});
      if(parent===parent.parent)break;parent=parent.parent;void parent.document;
    }}catch{/* Native local feedback remains available outside the same-origin host. */}
    return null;
  }
  const report={showError(message,data){return messages()?.showError(message,data)===true;},showInfo(message,seconds=3,data){return messages()?.showInfo(message,seconds,data)===true;}};
  window.CMHostMessages=Object.freeze(report);
  let localFeedback,localTimer;
  function clearLocal(){clearTimeout(localTimer);if(localFeedback){localFeedback.hidden=true;localFeedback.style.display='none';}}
  function localMessage(level,message,seconds=0){
    clearLocal();
    if(!localFeedback){localFeedback=document.createElement('div');localFeedback.dataset.caComponentFeedback='';localFeedback.style.cssText='position:fixed;top:8px;left:8px;right:8px;z-index:4000;padding:8px 12px;border:1px solid currentColor;background:var(--ca-ui-surface,#fff);font:inherit;display:flex;gap:8px;align-items:center';document.body.prepend(localFeedback);}
    localFeedback.replaceChildren();localFeedback.hidden=false;localFeedback.style.display='flex';localFeedback.setAttribute('role',level==='error'?'alert':'status');localFeedback.style.color=level==='error'?'var(--ca-ui-danger,#a12626)':'var(--ca-ui-info,#155576)';
    const text=document.createElement('span');text.textContent=String(message??'');text.style.flex='1';const close=document.createElement('button');close.type='button';close.textContent='×';close.setAttribute('aria-label','Fechar mensagem');close.onclick=clearLocal;localFeedback.append(text,close);
    if(level==='info')localTimer=setTimeout(clearLocal,Math.min(3600,Math.max(0,Number(seconds)||0))*1000);
  }
  window.showError??=(message,data)=>{if(!report.showError(message,data))localMessage('error',message);};
  window.showErro??=window.showError;
  window.showInfo??=(message,seconds=3,data)=>{if(!report.showInfo(message,seconds,data))localMessage('info',message,seconds);};
  document.addEventListener('click',event=>{if(event.target.closest('button,input[type=submit]')&&!event.target.closest('[data-ca-component-feedback]')){clearLocal();messages()?.beginOperation();}},true);
  window.addEventListener('error',event=>window.showError(event.message||'Erro no componente.',{errorType:event.error?.name||'Error'}));
  window.addEventListener('unhandledrejection',event=>window.showError(event.reason?.message||'Operação não concluída.',{errorType:event.reason?.name||'UnhandledRejection'}));
})();
