const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {JSDOM}=require('jsdom');
const source=fs.readFileSync(path.join(__dirname,'../cmail/static/mailbox-navigation.mjs'),'utf8').replace('export function','function').replaceAll('import.meta.url',JSON.stringify('http://localhost/email/static/mailbox-navigation.mjs'));
const settle=async()=>{for(let i=0;i<10;i++)await new Promise(r=>setImmediate(r));};
function fixture(){
 const dom=new JSDOM('<aside id="mail"></aside>',{url:'http://localhost/email/',runScripts:'outside-only'}),w=dom.window,calls=[],opened=[];
 w.fetch=async(url,opts)=>{calls.push({url,opts});return {ok:true,json:async()=>url.includes('/folders')?{folders:[{id:'INBOX',name:'Entrada',wellKnownName:'inbox'},{id:'SENT',name:'Enviados'}]}:url.includes('message-actions')?{actions:{send:true}}:{messages:[{id:'message',subject:'<img src=x onerror=alert(1)>',from:{name:'Remetente'},receivedAt:new Date().toISOString(),preview:'Resumo'}]}}};
 w.eval(source+';window.mount=mountMailboxNavigation');const api=w.mount(w.document.querySelector('aside'),{basePath:'/email',onMessage:item=>opened.push(item)});
 return {dom,w,api,calls,opened};
}
test('shared list renders safely, toggles folder/search and sends the query to the server',async()=>{
 const f=fixture();await settle();const d=f.w.document;
 assert.equal(d.querySelector('.cmail-navigation-item img'),null);assert.match(d.querySelector('strong').textContent,/<img/);
 d.querySelector('.cmail-navigation-item').click();assert.deepEqual(JSON.parse(JSON.stringify(f.opened)),[{folder:'INBOX',id:'message'}]);
 d.querySelector('button[aria-label="Buscar e-mails"]').click();assert.equal(d.querySelector('select').hidden,true);
 const q=d.querySelector('input');q.value='proposta antiga';q.dispatchEvent(new f.w.Event('input'));q.dispatchEvent(new f.w.KeyboardEvent('keydown',{key:'Enter'}));await settle();
 const url=new URL(f.calls.filter(c=>c.url.includes('/messages?')).at(-1).url,'http://localhost');assert.equal(url.searchParams.get('q'),'proposta antiga');assert.equal(url.searchParams.get('folder'),'INBOX');
 assert.ok(f.calls.every(c=>!c.opts?.method||c.opts.method==='GET'));f.api.dispose();f.dom.window.close();
});
test('late search responses and disposed navigation cannot overwrite the current list',async()=>{
 const f=fixture();await settle();const pending=[];
 f.w.fetch=(url,opts)=>new Promise(resolve=>pending.push({url,opts,resolve}));
 const first=f.api.reload(),second=f.api.reload();assert.equal(pending[0].opts.signal.aborted,true);
 pending[1].resolve({ok:true,json:async()=>({messages:[{id:'fresh',subject:'Atual'}]})});await second;
 pending[0].resolve({ok:true,json:async()=>({messages:[{id:'stale',subject:'Antigo'}]})});await first;
 assert.equal(f.w.document.querySelector('[data-mail-id]').dataset.mailId,'fresh');f.api.dispose();assert.equal(f.w.document.querySelectorAll('[data-mail-id]').length,0);f.dom.window.close();
});
