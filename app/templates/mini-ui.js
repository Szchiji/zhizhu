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
function mountTgBars(){
  document.querySelectorAll('.tgbar[data-for]').forEach(bar=>{
    if(bar.dataset.ready) return;
    const id=bar.getAttribute('data-for');
    const phKind=bar.getAttribute('data-ph')||'';
    TG_TOOLS.forEach(tool=>{
      const b=document.createElement('button');
      b.type='button'; b.textContent=tool.label; b.title=tool.title||tool.label;
      b.addEventListener('click',()=>{
        const ta=document.getElementById(id); if(!ta) return;
        if(tool.link) insertLink(ta); else wrapSelection(ta,tool.wrap[0],tool.wrap[1]);
      });
      bar.appendChild(b);
    });
    const phList=phKind==='card'?TG_PH_CARD:(phKind==='home'?TG_PH_HOME:null);
    if(phList){
      const phbar=document.createElement('div');
      phbar.className='phbar';
      phList.forEach(ph=>{
        const b=document.createElement('button');
        b.type='button'; b.textContent=ph.label; b.title='插入占位符 '+ph.value;
        b.addEventListener('click',()=>{
          const ta=document.getElementById(id); if(!ta) return;
          insertAtCursor(ta,ph.value);
        });
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
        const ta=document.getElementById(id); if(!ta) return;
        const idx=sel.value;
        if(idx===''){show(err,'请先选择一个自定义表情');return;}
        insertCustomEmoji(ta,TG_CUSTOM_EMOJI[Number(idx)]);
      };
      btn.addEventListener('click',doInsert);
      sel.addEventListener('change',()=>{ if(sel.value!=='') doInsert(); });
      const pasteBtn=document.createElement('button');
      pasteBtn.type='button'; pasteBtn.textContent='粘贴ID'; pasteBtn.title='粘贴自定义 emoji-id';
      pasteBtn.addEventListener('click',()=>{
        const ta=document.getElementById(id); if(!ta) return;
        promptCustomEmoji(ta);
      });
      emobar.appendChild(sel); emobar.appendChild(btn); emobar.appendChild(pasteBtn);
      const anchor=bar.parentNode.querySelector('.phbar')||bar;
      anchor.parentNode.insertBefore(emobar, anchor.nextSibling);
    }
    bar.dataset.ready='1';
  });
}
mountTgBars();

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
    _cardLoaded=true;
    if(btn) btn.disabled=false;
  }catch(e){}
}
async function saveCardTpl(){
  if(!_cardLoaded){show(err,'模板尚未加载完成，请稍候再保存');return;}
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
    _cardLoaded=true;
    const btn=document.getElementById('btnsavecard'); if(btn) btn.disabled=false;
    show(ok,'已套用并保存格式包。可再微调后点「保存模板」');
  }catch(e){show(err,e.message);}
}
