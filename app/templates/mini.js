const tg=window.Telegram.WebApp;tg.ready();tg.expand();
const user=(tg.initDataUnsafe&&tg.initDataUnsafe.user)||null;
const initData=tg.initData||'';
const err=document.getElementById('err'),ok=document.getElementById('ok');
function show(el,msg){err.style.display='none';ok.style.display='none';el.style.display='block';el.textContent=msg;}
function tab(name){
['pay','q','me','adm'].forEach(n=>document.getElementById('tab-'+n).classList.toggle('hidden',n!==name));
['pay','q','me','adm'].forEach((n,i)=>document.getElementById('n'+(i+1)).classList.toggle('on',n===name));
if(name==='me'){loadMe();loadOrders();} if(name==='adm'){loadAdmin();}
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
if(j.matches&&j.matches.length) html+='<div class="olist">'+j.matches.map(u=>'<div onclick="document.getElementById(\'q\').value=\'@'+u.username+'\';lookup()">@'+u.username+' · '+(u.display_name||'')+'</div>').join('')+'</div>';
html+='<div class="idcard">'+(j.found?j.card:('@'+(j.query||q)+' 暂无官方登记'))+'</div>';
document.getElementById('qtext').innerHTML=html;
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
el.innerHTML=j.users.map(u=>'<div>@'+(u.username||'无用户名')+' · '+(u.display_name||'')+' · ID '+u.tg_id+' · '+u.status+' · '+(u.paid_until||'')+'<br><button class="ghost" style="margin-top:6px" onclick="fillBind('+u.tg_id+',\''+(u.username||'')+'\',\''+(u.display_name||'')+'\')">补登记</button> <button class="ghost" onclick="userAct(\'user_block\','+u.tg_id+')">拉黑</button> <button class="ghost" onclick="userAct(\'user_unblock\','+u.tg_id+')">解除</button> <button class="ghost" onclick="userAct(\'user_delete\','+u.tg_id+')">删除</button></div>').join('');
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
document.getElementById('achannel').value=j.force_channel||''; loadCardTpl(); window._ch=j.force_channel_on==='1'; document.getElementById('achon').textContent=window._ch?'强制订阅：开':'强制订阅：关';
const hm=j.home||{}; document.getElementById('htitle').value=hm.title||'';
document.getElementById('hbody0').value=hm.body_unpaid||''; document.getElementById('hbody1').value=hm.body_paid||'';
document.getElementById('hhelp').value=hm.help||'';
const bt=hm.btns||[];
['hb1','hb2','hb3'].forEach((id,i)=>{document.getElementById(id).value=(bt[i]&&bt[i].label)||'';});
['ha1','ha2','ha3'].forEach((id,i)=>{document.getElementById(id).value=(bt[i]&&bt[i].action)||'mini';});
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
document.getElementById('apend').innerHTML=pend.length?pend.map(o=>'<div onclick="document.getElementById(\'acode\').value=\''+o.code+'\'"><b>'+o.code+'</b> · '+o.amount+'U · '+o.status+'</div>').join(''):'';
document.getElementById('aorders').innerHTML=rows.length?rows.map(o=>'<div onclick="document.getElementById(\'acode\').value=\''+o.code+'\'"><b>'+o.code+'</b> · '+(o.rail||'')+' · '+o.amount+' · '+o.status+(o.tg_id?(' · TG '+o.tg_id):'')+'</div>').join(''):'未找到';
}catch(e){show(err,e.message);}
}
async function confirmOrder(){try{await api('/api/mini/admin',{action:'confirm',code:document.getElementById('acode').value,txid:document.getElementById('atxid').value});show(ok,'订单已确认');}catch(e){show(err,e.message);}}
async function saveHome(){
const btns=[1,2,3].map(i=>({label:document.getElementById('hb'+i).value,action:document.getElementById('ha'+i).value})).filter(x=>x.label);
try{await api('/api/mini/admin',{action:'home',title:document.getElementById('htitle').value,body_unpaid:document.getElementById('hbody0').value,body_paid:document.getElementById('hbody1').value,help:document.getElementById('hhelp').value,btns:btns});show(ok,'首页已保存，重新 /start 查看');}catch(e){show(err,e.message);}}
async function save(){try{await api('/api/mini/profile',{display_name:document.getElementById('display').value,card_text:document.getElementById('card').value,username:user&&user.username});show(ok,'资料已生效');}catch(e){show(err,e.message);}}
loadMe();
async function loadCardTpl(){
try{
const j=await fetch('/api/mini/admin/card?user_id='+(user&&user.id||'')+'&init_data='+encodeURIComponent(initData)).then(r=>r.json());
if(j.error||!j.card_tpl) return;
const t=j.card_tpl;
document.getElementById('ctpaid').value=t.paid||'';
document.getElementById('ctunpaid').value=t.unpaid||'';
document.getElementById('ctissuer').value=t.issuer||'';
}catch(e){}
}
async function saveCardTpl(){
try{
await api('/api/mini/admin/card',{paid:document.getElementById('ctpaid').value,unpaid:document.getElementById('ctunpaid').value,issuer:document.getElementById('ctissuer').value});
show(ok,'卡片模板已保存');
}catch(e){show(err,e.message);}
}
async function cardPack(pack){
try{
const j=await api('/api/mini/admin/card',{apply_pack:true,pack:pack});
const t=j.card_tpl||{};
document.getElementById('ctpaid').value=t.paid||'';
document.getElementById('ctunpaid').value=t.unpaid||'';
document.getElementById('ctissuer').value=t.issuer||'';
show(ok,'已套用格式包');
}catch(e){show(err,e.message);}
}
