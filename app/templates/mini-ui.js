/* —— Telegram HTML toolbar —— */
const TG_TOOLS=[
  {label:'粗体',title:'粗体 <b>…</b>',wrap:['<b>','</b>']},
  {label:'斜体',title:'斜体 <i>…</i>',wrap:['<i>','</i>']},
  {label:'下划线',title:'下划线 <u>…</u>',wrap:['<u>','</u>']},
  {label:'删除线',title:'删除线 <s>…</s>',wrap:['<s>','</s>']},
  {label:'代码',title:'行内代码 <code>…</code>',wrap:['<code>','</code>']},
  {label:'代码块',title:'代码块 <pre>…</pre>',wrap:['<pre>','</pre>']},
  {label:'链接',title:'链接 <a href>…</a>',link:true},
  {label:'引用',title:'引用 <blockquote>…</blockquote>',wrap:['<blockquote>','</blockquote>']},
  {label:'可展开',title:'可展开引用 <blockquote expandable>',wrap:['<blockquote expandable>','</blockquote>']},
  {label:'遮罩',title:'遮罩/剧透 <tg-spoiler>…</tg-spoiler>',wrap:['<tg-spoiler>','</tg-spoiler>']},
];
const TG_PH_CARD=[
  {label:'{正文}',value:'{正文}'},
  {label:'{品牌}',value:'{品牌}'},
  {label:'{姓名}',value:'{姓名}'},
  {label:'{账号}',value:'{账号}'},
  {label:'{ID}',value:'{ID}'},
  {label:'{有效期}',value:'{有效期}'},
  {label:'{查询词}',value:'{查询词}'},
  {label:'{机器人}',value:'{机器人}'},
];
const TG_PH_HOME=[
  {label:'{品牌}',value:'{品牌}'},
  {label:'{机器人}',value:'{机器人}'},
  {label:'{到期}',value:'{到期}'},
  {label:'{账号}',value:'{账号}'},
  {label:'{姓名}',value:'{姓名}'},
];
/* Curated public custom emoji ids (fallback unicode). Animated render usually needs Fragment username. */
const TG_CUSTOM_EMOJI=[
  {id:'5368324170671202286',fallback:'👍',name:'赞'},
  {id:'5456140674028019486',fallback:'🚨',name:'紧急'},
  {id:'5224607267797606837',fallback:'⚡',name:'闪电'},
  {id:'5260293700088511294',fallback:'🚫',name:'禁止'},
  {id:'5240241223632954241',fallback:'❌',name:'取消'},
  {id:'5274099962655816924',fallback:'❗',name:'叹号'},
  {id:'5447644880824181073',fallback:'⚠️',name:'警告'},
  {id:'5172484558305625218',fallback:'⭐',name:'星星'},
  {id:'4996980495100150380',fallback:'❤️',name:'红心'},
  {id:'5931415565955503486',fallback:'🤖',name:'机器人'},
  {id:'4999005636604723783',fallback:'🐙',name:'GitHub'},
  {id:'4927197721900614739',fallback:'🔴',name:'直播'},
];
const CARD_TPL_IDS=['ctpaid','ctunpaid','ctissuer'];
const CARD_EMO_LABELS={ctpaid:'已登记卡 · 自定义表情',ctunpaid:'未登记卡 · 自定义表情',ctissuer:'出具方卡 · 自定义表情'};
const WYSIWYG_IDS=new Set(CARD_TPL_IDS);
const visEditors={};
let activeVisId=null;

function wrapSelection(ta,before,after){
  const start=ta.selectionStart||0,end=ta.selectionEnd||0;
  const val=ta.value||'';
  const selected=val.slice(start,end)||'文本';
  ta.value=val.slice(0,start)+before+selected+after+val.slice(end);
  const caret=start+before.length+selected.length+after.length;
  ta.focus(); ta.setSelectionRange(caret,caret);
}
function insertAtCursor(ta,text){
  const start=ta.selectionStart||0,end=ta.selectionEnd||0;
  const val=ta.value||'';
  ta.value=val.slice(0,start)+text+val.slice(end);
  const caret=start+text.length;
  ta.focus(); ta.setSelectionRange(caret,caret);
}
function insertLink(ta){
  let href='';
  try{href=window.prompt('链接地址（http/https/tg）','https://')||'';}catch(e){return;}
  href=String(href).trim();
  if(!new RegExp('^(https?://|tg://)','i').test(href)){show(err,'仅支持 http/https/tg 链接');return;}
  wrapSelection(ta,'<a href="'+href+'">','</a>');
}
function insertCustomEmoji(ta,item){
  if(!item) return;
  insertAtCursor(ta,'<tg-emoji emoji-id="'+item.id+'">'+item.fallback+'</tg-emoji>');
}
function promptCustomEmoji(ta){
  let raw='',fb='⭐';
  try{raw=window.prompt('粘贴自定义表情 emoji-id（纯数字）','')||'';}catch(e){return;}
  raw=String(raw).trim();
  const m=raw.match(/(\d{5,})/);
  if(!m){show(err,'请输入有效的数字 emoji-id');return;}
  try{fb=window.prompt('后备 Unicode 表情（客户端不支持自定义时显示）',fb)||fb;}catch(e){}
  fb=String(fb||'⭐').trim()||'⭐';
  insertCustomEmoji(ta,{id:m[1],fallback:fb});
}

function escAttr(s){return String(s||'').replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;');}
function tgHtmlToVis(raw){
  const src=String(raw||'');
  const withBr=src.replace(/\n/g,'<br>');
  let doc;
  try{doc=new DOMParser().parseFromString('<div id="r">'+withBr+'</div>','text/html');}
  catch(e){const d=document.createElement('div');d.textContent=src;return d.innerHTML.replace(/\n/g,'<br>');}
  const root=doc.getElementById('r')||doc.body;
  root.querySelectorAll('tg-emoji').forEach(el=>{
    const eid=el.getAttribute('emoji-id')||'';
    const fb=el.textContent||'⭐';
    const chip=doc.createElement('span');
    chip.className='tg-emoji-chip';
    chip.setAttribute('data-emoji-id',eid);
    chip.setAttribute('contenteditable','false');
    chip.title='emoji-id '+eid;
    chip.textContent=fb;
    el.parentNode.replaceChild(chip,el);
  });
  root.querySelectorAll('tg-spoiler').forEach(el=>{
    const sp=doc.createElement('span');
    sp.className='tg-spoiler';
    sp.setAttribute('data-tg','spoiler');
    while(el.firstChild) sp.appendChild(el.firstChild);
    el.parentNode.replaceChild(sp,el);
  });
  const walkText=(node)=>{
    if(!node) return;
    if(node.nodeType===3){
      const t=node.nodeValue||'';
      if(t.indexOf('{')<0) return;
      const re=/(\{[^{}]+\})/g;
      if(!re.test(t)) return;
      re.lastIndex=0;
      const frag=doc.createDocumentFragment();
      let last=0,m;
      while((m=re.exec(t))){
        if(m.index>last) frag.appendChild(doc.createTextNode(t.slice(last,m.index)));
        const tok=doc.createElement('span');
        tok.className='ph-token';
        tok.setAttribute('contenteditable','false');
        tok.textContent=m[1];
        frag.appendChild(tok);
        last=m.index+m[1].length;
      }
      if(last<t.length) frag.appendChild(doc.createTextNode(t.slice(last)));
      node.parentNode.replaceChild(frag,node);
      return;
    }
    if(node.nodeType===1){
      if(node.classList&&(node.classList.contains('tg-emoji-chip')||node.classList.contains('ph-token'))) return;
      Array.from(node.childNodes).forEach(walkText);
    }
  };
  Array.from(root.childNodes).forEach(walkText);
  return root.innerHTML;
}
function serializeVisNode(node){
  if(!node) return '';
  if(node.nodeType===3) return node.nodeValue||'';
  if(node.nodeType!==1) return '';
  const name=(node.tagName||'').toLowerCase();
  if(node.classList&&node.classList.contains('tg-emoji-chip')){
    const eid=node.getAttribute('data-emoji-id')||'';
    const fb=node.textContent||'⭐';
    return '<tg-emoji emoji-id="'+escAttr(eid)+'">'+fb+'</tg-emoji>';
  }
  if(node.classList&&node.classList.contains('ph-token')) return node.textContent||'';
  if((node.classList&&node.classList.contains('tg-spoiler'))||node.getAttribute('data-tg')==='spoiler'){
    return '<tg-spoiler>'+Array.from(node.childNodes).map(serializeVisNode).join('')+'</tg-spoiler>';
  }
  if(name==='br') return '\n';
  const kids=()=>Array.from(node.childNodes).map(serializeVisNode).join('');
  if(name==='div'||name==='p'){
    let inner=kids();
    if(inner&&!inner.endsWith('\n')) inner+='\n';
    return inner;
  }
  const map={b:'b',strong:'b',i:'i',em:'i',u:'u',ins:'u',s:'s',strike:'s',del:'s',code:'code',pre:'pre',a:'a',blockquote:'blockquote'};
  const mapped=map[name];
  if(mapped==='a'){
    const href=node.getAttribute('href')||'';
    const inner=kids();
    if(/^(https?:\/\/|tg:\/\/)/i.test(href)) return '<a href="'+escAttr(href)+'">'+inner+'</a>';
    return inner;
  }
  if(mapped==='blockquote'){
    const exp=node.hasAttribute('expandable')?' expandable':'';
    return '<blockquote'+exp+'>'+kids()+'</blockquote>';
  }
  if(mapped) return '<'+mapped+'>'+kids()+'</'+mapped+'>';
  if(name==='span') return kids();
  return kids();
}
function visToTgHtml(visEl){
  if(!visEl) return '';
  return Array.from(visEl.childNodes).map(serializeVisNode).join('').replace(/\n+$/,'');
}
function syncVisToTa(id){
  const ta=document.getElementById(id);
  const ed=visEditors[id]||document.getElementById(id+'-vis');
  if(!ta||!ed) return;
  ta.value=visToTgHtml(ed);
}
function syncAllVisToTa(){ CARD_TPL_IDS.forEach(syncVisToTa); }
function paintVisFromTa(id){
  const ta=document.getElementById(id);
  const ed=visEditors[id]||document.getElementById(id+'-vis');
  if(!ta||!ed) return;
  ed.innerHTML=tgHtmlToVis(ta.value||'');
}
function paintAllVisFromTa(){ CARD_TPL_IDS.forEach(paintVisFromTa); }
function getVisRange(ed){
  const sel=window.getSelection();
  if(!sel||!sel.rangeCount) return null;
  const range=sel.getRangeAt(0);
  if(!ed.contains(range.commonAncestorContainer)) return null;
  return range;
}
function wrapVisSelection(ed,tag,attrs){
  ed.focus();
  let range=getVisRange(ed);
  if(!range){
    range=document.createRange();
    range.selectNodeContents(ed);
    range.collapse(false);
    const sel=window.getSelection(); sel.removeAllRanges(); sel.addRange(range);
  }
  const el=document.createElement(tag);
  if(attrs){ Object.keys(attrs).forEach(k=>{ if(attrs[k]===''||attrs[k]==null) el.setAttribute(k,''); else el.setAttribute(k,attrs[k]); }); }
  try{
    if(range.collapsed){
      el.textContent='文本';
      range.insertNode(el);
      const r2=document.createRange(); r2.selectNodeContents(el); r2.collapse(false);
      const sel=window.getSelection(); sel.removeAllRanges(); sel.addRange(r2);
    }else{
      try{ range.surroundContents(el); }
      catch(e){ const frag=range.extractContents(); el.appendChild(frag); range.insertNode(el); }
    }
  }catch(e){}
  syncVisToTa(ed.getAttribute('data-for'));
}
function insertVisNode(ed,node){
  ed.focus();
  let range=getVisRange(ed);
  if(!range){
    range=document.createRange();
    range.selectNodeContents(ed);
    range.collapse(false);
  }
  range.deleteContents();
  range.insertNode(node);
  range.setStartAfter(node); range.collapse(true);
  const sel=window.getSelection(); sel.removeAllRanges(); sel.addRange(range);
  syncVisToTa(ed.getAttribute('data-for'));
}
function insertVisPlaceholder(ed,value){
  const tok=document.createElement('span');
  tok.className='ph-token';
  tok.setAttribute('contenteditable','false');
  tok.textContent=value;
  insertVisNode(ed,tok);
}
function insertVisEmoji(ed,item){
  if(!item) return;
  const chip=document.createElement('span');
  chip.className='tg-emoji-chip';
  chip.setAttribute('data-emoji-id',item.id);
  chip.setAttribute('contenteditable','false');
  chip.title='emoji-id '+item.id;
  chip.textContent=item.fallback||'⭐';
  insertVisNode(ed,chip);
}
function insertVisLink(ed){
  let href='';
  try{href=window.prompt('链接地址（http/https/tg）','https://')||'';}catch(e){return;}
  href=String(href).trim();
  if(!new RegExp('^(https?://|tg://)','i').test(href)){show(err,'仅支持 http/https/tg 链接');return;}
  wrapVisSelection(ed,'a',{href:href});
}
function promptVisCustomEmoji(ed){
  let raw='',fb='⭐';
  try{raw=window.prompt('粘贴自定义表情 emoji-id（纯数字）','')||'';}catch(e){return;}
  raw=String(raw).trim();
  const m=raw.match(/(\d{5,})/);
  if(!m){show(err,'请输入有效的数字 emoji-id');return;}
  try{fb=window.prompt('后备 Unicode 表情（客户端不支持自定义时显示）',fb)||fb;}catch(e){}
  fb=String(fb||'⭐').trim()||'⭐';
  insertVisEmoji(ed,{id:m[1],fallback:fb});
}
function toolTag(tool){
  if(!tool||!tool.wrap) return null;
  const open=tool.wrap[0]||'';
  if(open.indexOf('blockquote expandable')>=0) return {tag:'blockquote',attrs:{expandable:''}};
  if(open.indexOf('blockquote')>=0) return {tag:'blockquote',attrs:null};
  if(open.indexOf('tg-spoiler')>=0) return {tag:'span',attrs:{'class':'tg-spoiler','data-tg':'spoiler'}};
  if(open.indexOf('<pre>')>=0) return {tag:'pre',attrs:null};
  if(open.indexOf('<code>')>=0) return {tag:'code',attrs:null};
  if(open.indexOf('<b>')>=0) return {tag:'b',attrs:null,cmd:'bold'};
  if(open.indexOf('<i>')>=0) return {tag:'i',attrs:null,cmd:'italic'};
  if(open.indexOf('<u>')>=0) return {tag:'u',attrs:null,cmd:'underline'};
  if(open.indexOf('<s>')>=0) return {tag:'s',attrs:null,cmd:'strikeThrough'};
  return null;
}
function applyToolToTarget(id,tool){
  if(WYSIWYG_IDS.has(id)){
    const ed=visEditors[id]||document.getElementById(id+'-vis');
    if(!ed) return;
    activeVisId=id;
    ed.focus();
    if(tool.link){ insertVisLink(ed); return; }
    const meta=toolTag(tool);
    if(meta&&meta.cmd && (!meta.tag || meta.tag==='b'||meta.tag==='i'||meta.tag==='u'||meta.tag==='s')){
      try{ document.execCommand(meta.cmd); }catch(e){}
      syncVisToTa(id);
      return;
    }
    if(meta){ wrapVisSelection(ed,meta.tag,meta.attrs); return; }
    return;
  }
  const ta=document.getElementById(id); if(!ta) return;
  if(tool.link) insertLink(ta); else wrapSelection(ta,tool.wrap[0],tool.wrap[1]);
}
function insertIntoTarget(id,kind,payload){
  if(WYSIWYG_IDS.has(id)){
    const ed=visEditors[id]||document.getElementById(id+'-vis');
    if(!ed) return;
    activeVisId=id;
    if(kind==='ph') insertVisPlaceholder(ed,payload);
    else if(kind==='emoji') insertVisEmoji(ed,payload);
    else if(kind==='emoji-prompt') promptVisCustomEmoji(ed);
    return;
  }
  const ta=document.getElementById(id); if(!ta) return;
  if(kind==='ph') insertAtCursor(ta,payload);
  else if(kind==='emoji') insertCustomEmoji(ta,payload);
  else if(kind==='emoji-prompt') promptCustomEmoji(ta);
}
function mountCardWysiwyg(){
  CARD_TPL_IDS.forEach(id=>{
    const ed=document.getElementById(id+'-vis');
    if(!ed) return;
    visEditors[id]=ed;
    ed.addEventListener('focus',()=>{ activeVisId=id; });
    ed.addEventListener('input',()=>{ syncVisToTa(id); });
    ed.addEventListener('blur',()=>{ syncVisToTa(id); });
  });
}

function mountTgBars(){
  document.querySelectorAll('.tgbar[data-for]').forEach(bar=>{
    if(bar.dataset.ready) return;
    const id=bar.getAttribute('data-for');
    const phKind=bar.getAttribute('data-ph')||'';
    TG_TOOLS.forEach(tool=>{
      const b=document.createElement('button');
      b.type='button'; b.textContent=tool.label; b.title=tool.title||tool.label;
      b.addEventListener('click',()=>{ applyToolToTarget(id,tool); });
      bar.appendChild(b);
    });
    const phList=phKind==='card'?TG_PH_CARD:(phKind==='home'?TG_PH_HOME:null);
    if(phList){
      const phbar=document.createElement('div');
      phbar.className='phbar';
      phList.forEach(ph=>{
        const b=document.createElement('button');
        b.type='button'; b.textContent=ph.label; b.title='插入占位符 '+ph.value;
        b.addEventListener('click',()=>{ insertIntoTarget(id,'ph',ph.value); });
        phbar.appendChild(b);
      });
      bar.parentNode.insertBefore(phbar, bar.nextSibling);
    }
    if(phKind==='card'){
      const emobar=document.createElement('div');
      emobar.className='emobar';
      const sel=document.createElement('select');
      sel.title='插入 Telegram 自定义表情 <tg-emoji>';
      const opt0=document.createElement('option');
      opt0.value=''; opt0.textContent='自定义表情…';
      sel.appendChild(opt0);
      TG_CUSTOM_EMOJI.forEach((em,i)=>{
        const o=document.createElement('option');
        o.value=String(i);
        o.textContent=em.fallback+' '+em.name;
        sel.appendChild(o);
      });
      const btn=document.createElement('button');
      btn.type='button'; btn.textContent='插入表情'; btn.title='插入选中的自定义表情';
      const doInsert=()=>{
        const idx=sel.value;
        if(idx===''){show(err,'请先选择一个自定义表情');return;}
        insertIntoTarget(id,'emoji',TG_CUSTOM_EMOJI[Number(idx)]);
      };
      btn.addEventListener('click',doInsert);
      sel.addEventListener('change',()=>{ if(sel.value!=='') doInsert(); });
      const pasteBtn=document.createElement('button');
      pasteBtn.type='button'; pasteBtn.textContent='粘贴ID'; pasteBtn.title='粘贴自定义 emoji-id';
      pasteBtn.addEventListener('click',()=>{ insertIntoTarget(id,'emoji-prompt'); });
      const lab=document.createElement('div');
      lab.className='emobar-label';
      lab.textContent=CARD_EMO_LABELS[id]||'自定义表情';
      emobar.insertBefore(lab, emobar.firstChild);
      emobar.appendChild(sel); emobar.appendChild(btn); emobar.appendChild(pasteBtn);
      /* Scope to THIS bar's own phbar (not the first .phbar in the shared parent). */
      let ownPh=null;
      let sib=bar.nextSibling;
      while(sib && sib.nodeType!==1) sib=sib.nextSibling;
      if(sib && sib.classList && sib.classList.contains('phbar')) ownPh=sib;
      const anchor=ownPh||bar;
      anchor.parentNode.insertBefore(emobar, anchor.nextSibling);
    }
    bar.dataset.ready='1';
  });
}
mountTgBars();
mountCardWysiwyg();

async function loadCardTpl(){
  const btn=document.getElementById('btnsavecard');
  if(btn) btn.disabled=true;
  _cardLoaded=false;
  try{
    const j=await fetch('/api/mini/admin/card?user_id='+(user&&user.id||'')+'&init_data='+encodeURIComponent(initData)).then(r=>r.json());
    if(j.error||!j.card_tpl) return;
    const t=j.card_tpl;
    document.getElementById('ctpaid').value=t.paid||'';
    document.getElementById('ctunpaid').value=t.unpaid||'';
    document.getElementById('ctissuer').value=t.issuer||'';
    paintAllVisFromTa();
    _cardLoaded=true;
    if(btn) btn.disabled=false;
  }catch(e){}
}
async function saveCardTpl(){
  if(!_cardLoaded){show(err,'模板尚未加载完成，请稍候再保存');return;}
  syncAllVisToTa();
  try{
    const j=await api('/api/mini/admin/card',{
      parse:'html',
      paid:document.getElementById('ctpaid').value,
      unpaid:document.getElementById('ctunpaid').value,
      issuer:document.getElementById('ctissuer').value
    });
    const t=j.card_tpl||{};
    if(t.paid!=null) document.getElementById('ctpaid').value=t.paid;
    if(t.unpaid!=null) document.getElementById('ctunpaid').value=t.unpaid;
    if(t.issuer!=null) document.getElementById('ctissuer').value=t.issuer;
    paintAllVisFromTa();
    show(ok,'卡片模板已保存并生效。请重新查询一张卡核对；旧卡不会自动换文案');
  }catch(e){show(err,e.message);}
}
async function cardPack(pack){
  try{
    const j=await api('/api/mini/admin/card',{apply_pack:true,pack:pack});
    const t=j.card_tpl||{};
    document.getElementById('ctpaid').value=t.paid||'';
    document.getElementById('ctunpaid').value=t.unpaid||'';
    document.getElementById('ctissuer').value=t.issuer||'';
    paintAllVisFromTa();
    _cardLoaded=true;
    const btn=document.getElementById('btnsavecard'); if(btn) btn.disabled=false;
    show(ok,'已套用并保存格式包。可再微调后点「保存模板」');
  }catch(e){show(err,e.message);}
}


const PREVIEW_SAMPLES={'品牌':'示例品牌','机器人':'ExampleBot','姓名':'张三','账号':'@zhangsan','ID':'123456789','有效期':'2027-01-01 12:00','正文':'这是卡片正文示例','查询词':'@someone'};
const PREVIEW_TG_TAGS=new Set(['b','strong','i','em','u','ins','s','strike','del','code','pre','a','blockquote','br']);
function fillPreviewPlaceholders(src){let out=String(src||'');Object.keys(PREVIEW_SAMPLES).forEach(k=>{out=out.split('{'+k+'}').join(PREVIEW_SAMPLES[k]);});return out;}
function sanitizePreviewHtml(raw){
  const filled=fillPreviewPlaceholders(raw);
  let doc;try{doc=new DOMParser().parseFromString('<div id="pvroot">'+filled+'</div>','text/html');}catch(e){const d=document.createElement('div');d.textContent=filled;return d.innerHTML.replace(/\n/g,'<br>');}
  const root=doc.getElementById('pvroot')||doc.body;
  const walk=(node)=>{
    if(!node)return;
    if(node.nodeType===3){const parts=String(node.nodeValue||'').split('\n');if(parts.length<=1)return;const frag=doc.createDocumentFragment();parts.forEach((part,i)=>{if(i)frag.appendChild(doc.createElement('br'));if(part)frag.appendChild(doc.createTextNode(part));});node.parentNode.replaceChild(frag,node);return;}
    if(node.nodeType!==1){node.parentNode&&node.parentNode.removeChild(node);return;}
    const name=(node.tagName||'').toLowerCase();
    if(name==='tg-emoji'||name==='tg-spoiler'||(name==='span'&&(node.getAttribute('class')||'')==='tg-spoiler')){node.parentNode.replaceChild(doc.createTextNode(node.textContent||'▮'),node);return;}
    if(name==='script'||name==='style'||name==='iframe'||name==='img'){node.parentNode.removeChild(node);return;}
    if(!PREVIEW_TG_TAGS.has(name)&&name!=='div'){const kids=Array.from(node.childNodes);kids.forEach(walk);const parent=node.parentNode;if(!parent)return;while(node.firstChild)parent.insertBefore(node.firstChild,node);parent.removeChild(node);return;}
    Array.from(node.attributes||[]).forEach(a=>{const an=(a.name||'').toLowerCase();if(name==='a'&&an==='href'&&/^(https?:\/\/|tg:\/\/)/i.test(a.value||''))return;if(name==='blockquote'&&an==='expandable')return;node.removeAttribute(a.name);});
    Array.from(node.childNodes).forEach(walk);
  };
  Array.from(root.childNodes).forEach(walk);
  return root.innerHTML;
}
function previewTpl(textareaId){
  if(WYSIWYG_IDS.has(textareaId)) syncVisToTa(textareaId);
  const ta=document.getElementById(textareaId),box=document.getElementById('card-preview'),body=document.getElementById('card-preview-body');
  if(!ta||!box||!body)return;
  body.innerHTML=sanitizePreviewHtml(ta.value||'');
  box.classList.remove('hidden');
  try{box.scrollIntoView({behavior:'smooth',block:'nearest'});}catch(e){}
}
function admSec(name){
  document.querySelectorAll('.adm-sec').forEach(el=>el.classList.toggle('on',el.id==='asec-'+name));
  document.querySelectorAll('#admnav button').forEach(btn=>btn.classList.toggle('on',btn.getAttribute('data-sec')===name));
  if(name==='audit') loadAudits();
}
async function loadAudits(){
  const q=(document.getElementById('aq')&&document.getElementById('aq').value||'').trim();
  const action=(document.getElementById('aaction')&&document.getElementById('aaction').value||'').trim();
  try{
    const url='/api/mini/admin/audits?limit=50&q='+encodeURIComponent(q)+'&action='+encodeURIComponent(action)+'&user_id='+(user&&user.id||'')+'&init_data='+encodeURIComponent(initData);
    const j=await fetch(url).then(r=>r.json());
    if(j.error){show(err,j.error);return;}
    const el=document.getElementById('alist'); if(!el) return;
    const rows=j.audits||[];
    if(!rows.length){el.textContent='暂无审计记录';return;}
    el.innerHTML=rows.map(a=>'<div><b>#'+a.id+' · '+a.action+'</b><br>'+(a.created_at||'')+' · admin '+a.admin_tg_id+(a.target_type?(' · '+a.target_type+':'+(a.target_id||'')):'')+(a.detail?('<br>'+a.detail):'')+'</div>').join('');
  }catch(e){show(err,e.message);}
}
async function exportCsv(kind){
  try{
    const url='/api/mini/admin/export?kind='+encodeURIComponent(kind||'orders')+'&user_id='+(user&&user.id||'')+'&init_data='+encodeURIComponent(initData);
    const r=await fetch(url);
    if(!r.ok){let msg='导出失败';try{const j=await r.json(); if(j.error) msg=j.error;}catch(e){} show(err,msg); return;}
    const blob=await r.blob();
    const a=document.createElement('a'); a.href=URL.createObjectURL(blob);
    a.download=(kind==='users'?'users':'orders')+'.csv';
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(()=>URL.revokeObjectURL(a.href),1000); show(ok,'已开始下载');
  }catch(e){show(err,e.message);}
}
