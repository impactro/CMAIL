// Run with jsdom from the development test environment; no live provider calls.
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),{execFileSync}=require('node:child_process');
const {JSDOM}=require('jsdom');
const html=execFileSync(process.env.CMAIL_TEST_PYTHON||'python',['-s','-X','utf8','-c',"from cmail.web import TEMPLATES;print(TEMPLATES.env.get_template('index.html').render(authenticated=True,embedded=True,mode='demo',identity=None,csrf='fixture',base_path='/cm/cmail',webmail_enabled=True,auth_state='authorized'))"],{encoding:'utf8'});
const script=fs.readFileSync(path.join(__dirname,'../cmail/static/app.js'),'utf8');
async function fixture(actions,folder='INBOX',override){
 const dom=new JSDOM(html,{url:'http://localhost:5080/cm/cmail/?readerOnly=1&folder='+folder+'&messageId=target&hostRequest='+'a'.repeat(32),runScripts:'outside-only'}),w=dom.window,calls=[];
 w.fetch=async(url,options={})=>{calls.push({url,options});if(override){const result=override(url,options);if(result)return result;}return {ok:true,json:async()=>url.endsWith('message-actions')?{actions}:url.endsWith('folders')?{folders:[{id:'INBOX',name:'Entrada',wellKnownName:'inbox'},{id:'TRASH',name:'Lixeira',wellKnownName:'trash'}]}:{message:{id:'target',subject:'Assunto',from:{address:'fixture@example.test'},body:'<img src=x onerror=alert(1)>',to:[]}}};};
 w.eval(script);for(let i=0;i<12;i++)await new Promise(r=>setImmediate(r));return {dom,w,d:w.document,calls};
}
test('embedded native reader exposes authorized actions and stages replies without sending',async()=>{
 const f=await fixture({send:true,reply:true,forward:true,trash:true,setRead:true});
 assert.equal(f.d.body.classList.contains('cm-reader-only'),true);assert.equal(f.d.querySelector('#messageActions').hidden,false);
 for(const id of ['reply','forward','trashMessage','toggleRead'])assert.equal(f.d.getElementById(id).hidden,false);
 assert.equal(f.d.querySelector('#readBody img'),null);assert.match(f.d.querySelector('#readBody').textContent,/<img/);
 f.d.querySelector('#reply').click();assert.equal(f.d.querySelector('#composePane').hidden,false);assert.equal(f.d.querySelector('#to').value,'fixture@example.test');
 f.d.querySelector('#forward').click();assert.equal(f.d.querySelector('#composeTitle').textContent,'Encaminhar');
 assert.ok(f.calls.every(call=>!call.options.method||call.options.method==='GET'));assert.equal(f.calls.some(call=>/api\/messages\?/.test(call.url)),false);f.dom.window.close();
});
test('embedded native reader keeps denied actions hidden and refuses an unrelated folder',async()=>{
 const f=await fixture({reply:false,forward:false,trash:false,setRead:false});
 for(const id of ['reply','forward','trashMessage'])assert.equal(f.d.getElementById(id).hidden,true);f.dom.window.close();
 const invalid=await fixture({},'INVALID');assert.match(invalid.d.querySelector('#notice').textContent,/pasta selecionada/);
 assert.equal(invalid.calls.some(call=>call.url.includes('/messages/target')),false);invalid.dom.window.close();
});


test('auxiliary list failure cannot prevent the embedded message from opening',async()=>{
 const f=await fixture({lists:true},'INBOX',url=>url.endsWith('/lists')?Promise.reject(new Error('Lists unavailable')):null);
 assert.equal(f.d.querySelector('#readerContent').hidden,false);assert.equal(f.d.querySelector('#readSubject').textContent,'Assunto');
 const urls=f.calls.map(x=>x.url);assert.ok(urls.findIndex(x=>x.includes('/messages/target'))<urls.findIndex(x=>x.endsWith('/lists')));f.dom.window.close();
});

test('slow selection keeps old content and rejects an older response after a newer click',async()=>{
 const full=html,dom=new JSDOM(full,{url:'http://localhost:5080/cm/cmail/?legacy=1',runScripts:'outside-only'}),w=dom.window,d=w.document;
 const items=[{id:'a',subject:'A',from:{}},{id:'b',subject:'B',from:{}},{id:'c',subject:'C',from:{}}];let pending=[];
 const response=message=>({ok:true,json:async()=>({message})});
 w.fetch=async(url,options={})=>{
  if(url.endsWith('/message-actions'))return {ok:true,json:async()=>({actions:{}})};
  if(url.endsWith('/folders'))return {ok:true,json:async()=>({folders:[{id:'INBOX',wellKnownName:'inbox'}]})};
  if(url.includes('/messages?'))return {ok:true,json:async()=>({messages:items})};
  if(url.includes('/messages/a'))return response({...items[0],body:'Original body'});
  return new Promise(resolve=>pending.push({url,options,resolve}));
 };
 const settle=async()=>{for(let i=0;i<10;i++)await new Promise(r=>setImmediate(r));};
 w.eval(script);await settle();d.querySelector('[data-id="a"]').click();await settle();
 d.querySelector('[data-id="b"]').click();await settle();assert.equal(d.querySelector('#readerContent').hidden,false);assert.equal(d.querySelector('#readBody').textContent,'Original body');assert.equal(d.querySelector('#readerContent').getAttribute('aria-busy'),'true');
 d.querySelector('[data-id="c"]').click();await settle();assert.equal(pending[0].options.signal.aborted,true);
 pending[1].resolve(response({...items[2],body:'Newest'}));await settle();pending[0].resolve(response({...items[1],body:'Stale'}));await settle();
 assert.equal(d.querySelector('#readBody').textContent,'Newest');assert.equal(d.querySelector('#readerContent').hasAttribute('aria-busy'),false);
 d.querySelector('[data-id="b"]').click();await settle();pending[2].resolve({ok:false,json:async()=>({error:'Read failed'})});await settle();assert.equal(d.querySelector('#readBody').textContent,'Newest');assert.equal(d.querySelector('#readerContent').hidden,false);assert.equal(d.querySelector('#readerContent').hasAttribute('aria-busy'),false);dom.window.close();
});
