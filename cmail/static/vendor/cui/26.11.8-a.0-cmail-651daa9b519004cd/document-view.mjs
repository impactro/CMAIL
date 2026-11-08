// A trusted product template mounted in the current document, without an iframe.
// Transport, permitted assets, identity and controller selection belong to the host.
export async function mountTrustedView(root,{markup,styles=[],initialize,enhance=()=>{},signal,isHidden=()=>false}={}){
 if(typeof initialize!=='function')throw TypeError('Inicializador de apresentação obrigatório.');
 const document=root.ownerDocument,window=document.defaultView;
 const parsed=new window.DOMParser().parseFromString(String(markup),'text/html');
 // Templates never select executable code. The host injects its known controller.
 for(const node of parsed.querySelectorAll('script,link,base,meta[http-equiv]'))node.remove();
 for(const node of parsed.querySelectorAll('*'))for(const attribute of [...node.attributes]){
  if(/^on/i.test(attribute.name)||(['href','src','action','formaction'].includes(attribute.name)&&/^\s*(?:javascript|vbscript):/i.test(attribute.value)))node.removeAttribute(attribute.name);
 }
 const surface=document.createElement('div');surface.className='cui-document-view';const shadow=surface.attachShadow({mode:'open'});
 const html=document.createElement('html'),head=document.createElement('head'),body=document.importNode(parsed.body,true);
 for(const attribute of [...parsed.documentElement.attributes])html.setAttribute(attribute.name,attribute.value);
 html.append(head,body);shadow.append(html);
 const base=document.createElement('style');base.textContent=':host{display:block;height:100%;min-height:0;position:relative;container-type:size;contain:layout style;overflow:auto}html{height:100%;min-height:0}body{margin:0;min-height:100%;box-sizing:border-box}';head.append(base);
 for(const css of [...styles,...[...parsed.head.querySelectorAll('style')].map(node=>node.textContent)]){
  const style=document.createElement('style');style.textContent=css;head.append(style);
 }
 const virtual={documentElement:html,head,body,querySelector:selector=>html.querySelector(selector),querySelectorAll:selector=>html.querySelectorAll(selector),getElementById:id=>[...html.querySelectorAll('[id]')].find(node=>node.id===id)||null,addEventListener:shadow.addEventListener.bind(shadow),removeEventListener:shadow.removeEventListener.bind(shadow),dispatchEvent:shadow.dispatchEvent.bind(shadow)};
 const scope=new Proxy(document,{get(target,key){if(key==='activeElement')return shadow.activeElement;if(key==='hidden')return document.hidden||isHidden();if(key==='visibilityState')return document.hidden||isHidden()?'hidden':'visible';if(Object.hasOwn(virtual,key))return virtual[key];const value=Reflect.get(target,key,target);return typeof value==='function'?value.bind(target):value;}});
 let controller,disposed=false;const cleanup=new Set();
 const dispose=()=>{if(disposed)return;disposed=true;observer.disconnect();controller?.dispose?.();for(const callback of cleanup)callback();cleanup.clear();signal?.removeEventListener('abort',dispose);surface.remove();};
 const observer=new window.MutationObserver(records=>{for(const record of records)for(const node of record.addedNodes)if(node.nodeType===1)enhance(node);});
 observer.observe(body,{childList:true,subtree:true});enhance(body);
 try{
  if(signal?.aborted)throw new window.DOMException('Montagem cancelada.','AbortError');
  // Layout measurements and native dialog APIs need a connected DOM.
  root.append(surface);signal?.addEventListener('abort',dispose,{once:true});
  controller=await initialize(scope);
  if(disposed||signal?.aborted){controller?.dispose?.();throw new window.DOMException('Montagem cancelada.','AbortError');}
  enhance(body);
  return {surface,shadow,document:scope,dispose,onDispose(callback){if(disposed)callback();else cleanup.add(callback);}};
 }catch(error){dispose();throw error;}
}
