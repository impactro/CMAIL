// Generic navigation with explicit host actions. No URLs, requests, identity or persistence.
export function renderNavigation(root,items,{selectedId='',onOpen,actions=[]}={}){
 if(typeof onOpen!=='function')throw TypeError('Callback de seleção obrigatório.');
 const doc=root.ownerDocument,fragment=doc.createDocumentFragment();
 const focused=root.contains(doc.activeElement)?doc.activeElement.dataset.navigationId:null;
 for(const item of items){
  const row=doc.createElement('div');row.className='cui-menu-entry conversation-item'+(item.id===selectedId?' active':'');
  const open=doc.createElement('button');open.type='button';open.className='cui-menu-row conversation-open';
  open.dataset.navigationId=item.id;open.title=item.title;open.setAttribute('aria-pressed',String(item.id===selectedId));
  const title=doc.createElement('strong'),subtitle=doc.createElement('span');title.textContent=item.title;subtitle.textContent=item.subtitle||'';open.append(title,subtitle);
  open.addEventListener('click',()=>onOpen(item));row.append(open);
  for(const action of actions){
   const node=doc.createElement('button');node.type='button';node.className='cui-button cui-navigation-action'+(action.className?' '+action.className:'');
   node.textContent=action.icon||action.label;node.title=action.label;node.setAttribute('aria-label',action.label+' '+item.title);node.addEventListener('click',()=>action.invoke(item));row.append(node);
  }
  fragment.append(row);
 }
 root.replaceChildren(fragment);
 if(focused)[...root.querySelectorAll('[data-navigation-id]')].find(node=>node.dataset.navigationId===focused)?.focus({preventScroll:true});
}
