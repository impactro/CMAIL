import {mountMailboxNavigation} from './mailbox-navigation.mjs';
const base=document.body.dataset.base||'',reader=document.querySelector('#mail-reader'),compose=document.querySelector('#mail-compose'),empty=document.querySelector('#mail-empty');
let request='',selection=null;
const nonce=()=>Array.from(crypto.getRandomValues(new Uint8Array(16)),v=>v.toString(16).padStart(2,'0')).join('');
function open(item){selection=item;request=nonce();empty.hidden=true;compose.hidden=true;reader.hidden=false;reader.src=base+'/?'+new URLSearchParams({readerOnly:1,folder:item.folder,messageId:item.id,hostRequest:request});}
function write(settings=false){empty.hidden=true;reader.hidden=true;compose.hidden=false;if(!compose.src||settings)compose.src=base+'/?composeOnly=1'+(settings?'&settingsOnly=1':'');else compose.contentWindow?.postMessage({type:'cmail:compose-open'},location.origin);}
const navigation=mountMailboxNavigation(document.querySelector('#mail-navigation'),{basePath:base,onMessage:open,onCompose:()=>write()});
document.querySelector('#mail-template').onclick=()=>write(true);
window.addEventListener('message',event=>{if(event.origin!==location.origin)return;if(event.source===reader.contentWindow&&event.data?.request===request&&['cmail:message-changed','cmail:message-updated'].includes(event.data.type)){void navigation.reload();if(event.data.type==='cmail:message-changed'){reader.hidden=true;empty.hidden=false;selection=null}}else if(event.source===compose.contentWindow&&event.data?.type==='cmail:compose-closed'){compose.hidden=true;reader.hidden=!selection;empty.hidden=!!selection}});
