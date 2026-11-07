// Adopts an existing DOM while preserving product IDs and listeners.
const defaultAliases={
 'ca-shell':'cui-shell','ca-sidebar':'cui-sidebar','ca-topbar':'cui-topbar',
 'ca-field':'cui-field','ca-input':'cui-input','ca-form':'cui-form',
 'ca-table':'cui-table','ca-table-wrap':'cui-table-viewport','ca-empty-state':'cui-empty',
 'ca-dialog':'cui-dialog','ca-dialog-content':'cui-dialog-body',
 'ca-dialog-header':'cui-dialog-header','ca-dialog-footer':'cui-dialog-footer',
 'ca-page-header':'cui-topbar','ca-section-title':'cui-section-title'
};
const richContent='.message-body,.chat-data,.chat-html-frame,.chat-message,.chat-envelope';
export function adoptDocument(document,{aliases:hostAliases={}}={}){
 if(document?.nodeType!==9||!document.defaultView||document.defaultView.document!==document)throw TypeError('Documento CUI inválido.');
 for(const[key,value]of Object.entries(hostAliases))if(!/^[a-z][a-z0-9_-]*$/.test(key)||!/^cui-[a-z0-9-]+$/.test(value))throw TypeError('Alias de apresentação inválido.');
 const aliases={...defaultAliases,...hostAliases},aliasEntries=Object.entries(aliases);
 const candidates=[...Object.keys(aliases).map(name=>'.'+name),'button','input','select','textarea','label'].join(',');
 const window=document.defaultView;let disposed=false,started=false,observer;
 function enhance(root){
  if(disposed||!root?.querySelectorAll||root.closest?.(richContent))return;
  const nodes=root.nodeType===1?[root,...root.querySelectorAll(candidates)]:[...root.querySelectorAll(candidates)];
  for(const node of nodes){
   // CCR owns rich-message internals, including isolated documents.
   if(node.closest?.(richContent))continue;
   for(const [legacy,current]of aliasEntries)if(node.classList?.contains(legacy))node.classList.add(current);
   if(node.matches?.('button:not(.chat-message-action),input[type=submit]')){
    node.classList.add('cui-button');
    if(!node.dataset.tone)node.dataset.tone=node.matches('.danger-button,.ca-button--danger')?'danger':node.matches('.send-button,.ca-button--primary')?'primary':'secondary';
   }
   if(node.matches?.('input:not([type=checkbox]):not([type=radio]):not([type=file]):not([type=submit]):not([type=hidden]),select,textarea'))node.classList.add('cui-input');
   if(node.matches?.('label')&&!node.querySelector('input[type=checkbox],input[type=radio],input[type=file]'))node.classList.add('cui-field');
  }
 }
 function theme(){
  if(!document.body)return;
  document.body.classList.add('cui-root');
  const style=window.getComputedStyle(document.documentElement);
  for(const key of ['canvas','surface','text','muted','border','action','on-action','focus','danger','success','warning','radius','bubble-radius','sidebar-surface','sidebar-text','header-surface','header-text']){
   const value=style.getPropertyValue('--ca-ui-'+key).trim();
   if(value)document.body.style.setProperty('--cui-'+key,value);
  }
  const link=style.getPropertyValue('--ca-ui-link').trim()||style.getPropertyValue('--ca-ui-focus').trim();
  if(link)document.body.style.setProperty('--cui-link',link);
  const font=style.getPropertyValue('--ca-ui-font').trim();if(font)document.body.style.fontFamily=font;
 }
 const start=()=>{if(disposed||started||!document.body)return;started=true;theme();enhance(document.body);
  observer=new window.MutationObserver(records=>{for(const record of records)for(const node of record.addedNodes)if(node.nodeType===1)enhance(node);});
  observer.observe(document.body,{childList:true,subtree:true});
 };
 const themeObserver=new window.MutationObserver(theme);
 themeObserver.observe(document.documentElement,{attributes:true,attributeFilter:['style','class','data-ca-theme','data-theme']});
 const refresh=()=>theme();document.addEventListener('ca:theme-change',refresh);
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
 return {enhance,refreshTheme:theme,dispose(){if(disposed)return;disposed=true;observer?.disconnect();themeObserver.disconnect();document.removeEventListener('DOMContentLoaded',start);document.removeEventListener('ca:theme-change',refresh);}};
}
