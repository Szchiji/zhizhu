const tg=window.Telegram.WebApp;tg.ready();tg.expand();
const user=(tg.initDataUnsafe&&tg.initDataUnsafe.user)||null;
const initData=tg.initData||'';
const err=document.getElementById('err'),ok=document.getElementById('ok');
let _cardLoaded=false;
function show(el,msg){
  const text=String(msg||'');
  const title=(el===err)?'操作失败':'已完成';
  try{
    if(tg.showPopup){
      tg.showPopup({title:title,message:text,buttons:[{id:'ok',type:'ok',text:'好的'}]});
      return;
    }
    if(tg.showAlert){tg.showAlert(text);return;}
  }catch(e){}
  err.style.display='none';ok.style.display='none';
  el.style.display='block';el.textContent=text;
}
function tab(name){
['pay','q','me','adm'].forEach(n=>document.getElementById('tab-'+n).classList.toggle('hidden',n!==name));
['pay','q','me','adm'].forEach((n,i)=>document.getElementById('n'+(i+1)).classList.toggle('on',n===name));
if(name==='me'){loadMe();loadOrders();} if(name==='adm'){loadAdmin();}
}
function admSec(name){
  document.querySelectorAll('.adm-sec').forEach(el=>el.classList.toggle('on',el.id==='asec-'+name));
  document.querySelectorAll('#admnav button').forEach(btn=>btn.classList.toggle('on',btn.getAttribute('data-sec')===name));
}
if(user){
document.getElementById('uname').textContent=user.first_name+(user.last_name?(' '+user.last_name):'');
const av=document.getElementById('av');
if(user.photo_url) av.innerHTML='<img src="'+user.photo_url+'">'; else av.textContent=(user.first_name||'?').slice(0,1);
} else document.getElementById('uname').textContent='请从机器人打开';
async function api(path,body){
const r=await fetch(path,{method:body?'POST':'GET',headers:{'Content-Type':'application/json'},body:body?JSON.stringify(Object.assign({init_data:initData,user_id:user&&user.id},body)):undefined});
const j=await r.json(); if(!r.ok||j.error) throw new Error(j.error||'请求失败'); return j;
}
async function pay(btn,rail){
if(!user){show(err,'请从机器人打开');return;} btn.disabled=true;
try{
const j=await api('/api/mini/order',{plan:'year',rail:rail});
if(j.invoice&&tg.openInvoice){tg.openInvoice(j.invoice,async st=>{if(st==='paid'){show(ok,'支付成功');try{await api('/api/mini/stars-paid',{payload:j.payload||'',username:user&&user.username,display_name:user&&((user.first_name||'')+(user.last_name?(' '+user.last_name):''))});}catch(e){}loadMe();tab('me');}btn.disabled=false;});}
else if(j.address){
document.getElementById('checkout').classList.remove('hidden');
document.getElementById('oid').textContent=j.code; document.getElementById('oamt').textContent=j.amount+' USDT';
document.getElementById('ochain').textContent=(j.chain||'TRC20').toUpperCase(); document.getElementById('oaddr').textContent=j.address; window._addr=j.address;
show(ok,'订单号 '+j.code+' ，请转账后等待到账'); btn.disabled=false; watchPaid();
}
}catch(e){show(err,e.message);btn.disabled=false;}
}
async function watchPaid(){
const code=document.getElementById('oid').textContent.trim();
for(let i=0;i<48;i++){ await new Promise(r=>setTimeout(r,5000));
try{
const j=await fetch('/api/mini/orders?user_id='+user.id+'&init_data='+encodeURIComponent(initData)).then(r=>r.json());
const hit=(j.orders||[]).find(o=>o.code===code);
if(hit&&hit.status==='active'){
document.getElementById('checkout').classList.add('hidden');
show(ok,'续费已到账，时效已叠加');
loadMe();loadOrders();tab('me');return;
}
}catch(e){}}
}
function copyAddr(){if(window._addr) navigator.clipboard.writeText(window._addr).then(()=>show(ok,'地址已复制'));}
async function cancelPay(){ try{ await api('/api/mini/cancel',{code:document.getElementById('oid').textContent}); document.getElementById('checkout').classList.add('hidden'); show(ok,'订单已取消'); }catch(e){show(err,e.message);} }
async function lookup(){
const q=document.getElementById('q').value.trim();
try{
const j=await fetch('/api/mini/lookup?q='+encodeURIComponent(q)+'&user_id='+(user&&user.id||'')+'&init_data='+encodeURIComponent(initData)).then(r=>r.json());
const box=document.getElementById('qcard'); if(j.error){show(err,j.error);return;} box.classList.remove('hidden');
let html='';
if(j.matches&&j.matches.length){html+='<div class="olist">'+j.matches.map(u=>'<div class="pick" data-q="@'+u.username+'">@'+u.username+' · '+(u.display_name||'')+'</div>').join('')+'</div>';}
const body=j.found?(j.card||''):(j.card||('@'+(j.query||q)+' 暂无平台登记'));
html+='<div class="idcard"></div>';
document.getElementById('qtext').innerHTML=html;
document.getElementById('qtext').querySelector('.idcard').textContent=body;document.getElementById('qtext').querySelectorAll('.pick').forEach(el=>{el.onclick=()=>{document.getElementById('q').value=el.getAttribute('data-q');lookup();};});
}catch(e){show(err,e.message);}
}
async function loadMe(){
if(!user)return;
try{
const j=await fetch('/api/mini/me?user_id='+user.id+'&init_data='+encodeURIComponent(initData)+'&username='+encodeURIComponent(user.username||'')+'&display_name='+encodeURIComponent((user.first_name||'')+(user.last_name?(' '+user.last_name):''))).then(r=>r.json());
if(j.error){show(err,j.error);return;}
document.getElementById('status').textContent=j.paid?'已开通':'未开通';
document.getElementById('plan').textContent=j.plan_label||'—'; document.getElementById('until').textContent=j.paid_until||'—';
document.getElementById('display').value=j.display_name||''; document.getElementById('card').value=j.card_text||'';
document.getElementById('needpay').textContent=j.paid?'保存后立即用于查询出卡':'开通后才能保存资料';
if(j.is_admin) document.getElementById('n4').classList.remove('hidden');
}catch(e){show(err,e.message);}
}
async function loadOrders(){
if(!user)return;
try{ const j=await fetch('/api/mini/orders?user_id='+user.id+'&init_data='+encodeURIComponent(initData)).then(r=>r.json());
const el=document.getElementById('olist'); if(!j.orders||!j.orders.length){el.textContent='暂无';return;}
el.innerHTML=j.orders.map(o=>'<div><b>'+(o.code||'')+'</b><br>'+o.created+' · '+o.rail+' · '+o.amount+' · '+o.status+'</div>').join('');
}catch(e){}
}
async function searchUsers(){
const q=document.getElementById('uq').value.trim();
try{
const j=await fetch('/api/mini/admin/users?q='+encodeURIComponent(q)+'&user_id='+(user&&user.id||'')+'&init_data='+encodeURIComponent(initData)).then(r=>r.json());
if(j.error){show(err,j.error);return;} const el=document.getElementById('ulist');
if(!j.users||!j.users.length){el.textContent='未找到';return;}
el.innerHTML=j.users.map(u=>'<div>@'+(u.username||'无用户名')+' · '+(u.display_name||'')+' · ID '+u.tg_id+' · '+u.status+' · '+(u.paid_until||'')+'<br><button class="ghost fillb" style="margin-top:6px" data-tg="'+u.tg_id+'" data-un="'+(u.username||'')+'" data-dn="'+(u.display_name||'')+'">补登记</button>'+' <button class="ghost" data-act="user_block" data-tg="'+u.tg_id+'">拉黑</button>'+' <button class="ghost" data-act="user_unblock" data-tg="'+u.tg_id+'">解除</button>'+' <button class="ghost" data-act="user_delete" data-tg="'+u.tg_id+'">删除</button></div>').join('');el.querySelectorAll('.fillb').forEach(b=>b.onclick=()=>fillBind(b.getAttribute('data-tg'),b.getAttribute('data-un'),b.getAttribute('data-dn')));el.querySelectorAll('[data-act]').forEach(b=>b.onclick=()=>userAct(b.getAttribute('data-act'),b.getAttribute('data-tg')));
}catch(e){show(err,e.message);}
}
function fillBind(tg,uname,dname){document.getElementById('atgid').value=tg||'';document.getElementById('auname').value=uname||'';document.getElementById('aname').value=dname||'';}
async function bindUser(){ try{ await api('/api/mini/admin',{action:'user_bind',tg_id:document.getElementById('atgid').value,username:document.getElementById('auname').value,display_name:document.getElementById('aname').value}); show(ok,'已补登记'); searchUsers(); }catch(e){show(err,e.message);} }
async function addUser(){ try{ await api('/api/mini/admin',{action:'user_add',tg_id:document.getElementById('atgid').value,username:document.getElementById('auname').value,display_name:document.getElementById('aname').value,days:document.getElementById('adays').value}); show(ok,'已开通'); searchUsers(); }catch(e){show(err,e.message);} }
async function userAct(action,tg_id){ try{ await api('/api/mini/admin',{action:action,tg_id:tg_id}); show(ok,'已处理'); searchUsers(); }catch(e){show(err,e.message);} }
async function loadAdmin(){
try{
const j=await fetch('/api/mini/admin?user_id='+(user&&user.id||'')+'&init_data='+encodeURIComponent(initData)).then(r=>r.json());
if(j.error){show(err,j.error);return;}
document.getElementById('aboard').textContent=j.board||'';
document.getElementById('astars').value=j.stars||''; document.getElementById('ausdt').value=j.usdt||''; document.getElementById('aaddr').value=j.address||'';
document.getElementById('aclone').textContent=j.clone?'克隆：开':'克隆：关';
document.getElementById('rdays').value=j.remind_days||7; document.getElementById('rtext').value=j.remind_text||'';
window._remind=j.remind_enabled!=='0'; document.getElementById('renable').textContent=window._remind?'提醒：开':'提醒：关';
document.getElementById('achannel').value=j.force_channel||''; window._ch=j.force_channel_on==='1'; document.getElementById('achon').textContent=window._ch?'强制订阅：开':'强制订阅：关';
const hm=j.home||{}; document.getElementById('htitle').value=hm.title||''; document.getElementById('hbody0').value=hm.body_unpaid||''; document.getElementById('hbody1').value=hm.body_paid||'';
document.getElementById('hhelp').value=hm.help||'';
const bt=hm.btns||[];
['hb1','hb2','hb3'].forEach((id,i)=>{document.getElementById(id).value=(bt[i]&&bt[i].label)||'';});
['ha1','ha2','ha3'].forEach((id,i)=>{document.getElementById(id).value=(bt[i]&&bt[i].action)||'mini';});
await loadCardTpl();
}catch(e){show(err,e.message);}
}
async function setPrice(rail){try{await api('/api/mini/admin',{action:'price',rail:rail,amount:document.getElementById(rail==='stars'?'astars':'ausdt').value});show(ok,'价格已更新');loadAdmin();}catch(e){show(err,e.message);}}
async function setAddr(){try{await api('/api/mini/admin',{action:'addr',address:document.getElementById('aaddr').value});show(ok,'地址已保存');}catch(e){show(err,e.message);}}
async function saveRemind(){try{await api('/api/mini/admin',{action:'remind',days:document.getElementById('rdays').value,text:document.getElementById('rtext').value,enabled:window._remind?'1':'0'});show(ok,'提醒已保存');}catch(e){show(err,e.message);}}
async function toggleRemind(){window._remind=!window._remind;document.getElementById('renable').textContent=window._remind?'提醒：开':'提醒：关';saveRemind();}
async function saveChannel(){try{await api('/api/mini/admin',{action:'channel',channel:document.getElementById('achannel').value,enabled:window._ch?'1':'0'});show(ok,'频道已保存');}catch(e){show(err,e.message);}}
async function toggleChannel(){window._ch=!window._ch;document.getElementById('achon').textContent=window._ch?'强制订阅：开':'强制订阅：关';saveChannel();}
async function toggleClone(){try{const j=await api('/api/mini/admin',{action:'clone'});document.getElementById('aclone').textContent=j.clone?'克隆：开':'克隆：关';}catch(e){show(err,e.message);}}
async function searchOrders(){
const q=(document.getElementById('oq').value||'').trim().toLowerCase();
try{
const j=await fetch('/api/mini/admin?user_id='+(user&&user.id||'')+'&init_data='+encodeURIComponent(initData)).then(r=>r.json());
if(j.error){show(err,j.error);return;}
const hit=o=>!q||String(o.code||'').toLowerCase().includes(q)||String(o.tg_id||'').includes(q)||String(o.status||'').includes(q)||String(o.rail||'').includes(q);
const pend=(j.pending||[]).filter(hit);
const rows=(j.orders||[]).filter(hit);
document.getElementById('apend').innerHTML=pend.length?pend.map(o=>'<div class="ocode" data-c="'+o.code+'"><b>'+o.code+'</b> · '+o.amount+'U · '+o.status+'</div>').join(''):'';document.getElementById('apend').querySelectorAll('.ocode').forEach(el=>el.onclick=()=>{document.getElementById('acode').value=el.getAttribute('data-c');});
document.getElementById('aorders').innerHTML=rows.length?rows.map(o=>'<div class="ocode" data-c="'+o.code+'"><b>'+o.code+'</b> · '+(o.rail||'')+' · '+o.amount+' · '+o.status+(o.tg_id?(' · TG '+o.tg_id):'')+'</div>').join(''):'未找到';document.getElementById('aorders').querySelectorAll('.ocode').forEach(el=>el.onclick=()=>{document.getElementById('acode').value=el.getAttribute('data-c');});
}catch(e){show(err,e.message);}
}
async function confirmOrder(){try{await api('/api/mini/admin',{action:'confirm',code:document.getElementById('acode').value,txid:document.getElementById('atxid').value});show(ok,'订单已确认');}catch(e){show(err,e.message);}}
async function saveHome(){
const btns=[1,2,3].map(i=>({label:document.getElementById('hb'+i).value,action:document.getElementById('ha'+i).value})).filter(x=>x.label);
try{await api('/api/mini/admin',{action:'home',title:document.getElementById('htitle').value,body_unpaid:document.getElementById('hbody0').value,body_paid:document.getElementById('hbody1').value,help:document.getElementById('hhelp').value,btns:btns});show(ok,'首页已保存。请回机器人重新发送 /start');}catch(e){show(err,e.message);}}
async function save(){try{await api('/api/mini/profile',{display_name:document.getElementById('display').value,card_text:document.getElementById('card').value,username:user&&user.username});show(ok,'资料已生效');}catch(e){show(err,e.message);}}
loadMe();

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
