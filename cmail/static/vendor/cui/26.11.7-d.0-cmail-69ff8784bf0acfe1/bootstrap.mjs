// One frontend kernel per standalone document. No account, transport or authentication.
import * as CUI from './index.mjs';
import './compat/ca-modal.js';
import './compat/ui/index.js';
const key=Symbol.for('crania.cui.document');
export function startHost({profile='caw',aliases={},presentation={}}={}){
 if(window[key]){
  if(window[key].profile!==profile)throw Error('Perfis CUI diferentes no mesmo documento. Use montagem explícita.');
  return window.CUI;
 }
 const base=new URL('./',document.currentScript?.src||document.baseURI);
 let handle=CUI.adoptDocument(document,{aliases});
 const assets=Object.freeze({url(name){
  if(typeof name!=='string'||!name.split('/').every(part=>/^[a-zA-Z0-9][a-zA-Z0-9_.-]*$/.test(part)))throw TypeError('Recurso CUI inválido.');
  return new URL(name,base).href;
 }});
 window.CUI=Object.freeze({...CUI,profile,assets,presentation:Object.freeze({...presentation}),enhance:root=>handle.enhance(root),refreshTheme:()=>handle.refreshTheme()});
 window[key]=Object.freeze({profile});
 window.addEventListener('pagehide',()=>handle.dispose());
 window.addEventListener('pageshow',event=>{if(event.persisted)handle=CUI.adoptDocument(document,{aliases});});
 window.dispatchEvent(new Event('cui:ready'));
 return window.CUI;
}
