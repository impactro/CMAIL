// Mail rows are presentation only. Selection and network effects are supplied by CMAIL.
export function renderMailRows(list, items, {selected='', date=()=>'', onSelect=()=>{}}={}) {
 const doc=list.ownerDocument, fragment=doc.createDocumentFragment();
 const focus=list.contains(doc.activeElement)?doc.activeElement.dataset.mailId:null;
 const make=(tag,text='',cls='')=>{const node=doc.createElement(tag);node.textContent=text;node.className=cls;return node;};
 for(const item of items){
  const row=make('button','','cmail-navigation-item cui-menu-row');row.type='button';row.dataset.mailId=item.id;row.setAttribute('aria-current',item.id===selected?'page':'false');
  const heading=make('span','','cmail-message-heading'),subject=make('strong',item.subject||'(sem assunto)','cui-menu-title'),stamp=make('time',date(item.receivedAt),'cmail-message-date');
  subject.title=subject.textContent;if(item.receivedAt)stamp.dateTime=item.receivedAt;
  const sender=make('span',item.from?.name||item.from?.address||'Remetente não informado','cmail-message-sender');sender.title=item.from?.address||sender.textContent;
  heading.append(subject,stamp);row.append(heading,sender,make('span',item.preview||'','cmail-message-preview cui-menu-subtitle'));
  row.onclick=()=>onSelect(item,row);fragment.append(row);
 }
 list.replaceChildren(fragment);
 if(focus)[...list.children].find(row=>row.dataset.mailId===focus)?.focus({preventScroll:true});
}
