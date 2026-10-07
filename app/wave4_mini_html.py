"""Wave4: /mini HTML cache-bust + last-wins pay handler."""
from __future__ import annotations

import logging

from fastapi import Request
from fastapi.responses import HTMLResponse

from app.static_ver import MINI_ASSET_VER
from app.wave_card_wysiwyg import patch_mini_html

log = logging.getLogger("zhizhu.wave4_mini")

_PAY_BOOT = r"""<script>
window.__payBoot36=true;
window.__couponPayWrap=true;
(function(){
function box(ok,msg){
var t=String(msg||'');
var a=document.getElementById(ok?'ok':'err');
if(a){a.style.display='block';a.textContent=t;}
var b=document.getElementById(ok?'err':'ok');
if(b) b.style.display='none';
var h=document.getElementById('pay-coupon-hint');
if(h) h.textContent=t;
}
function code(){return ((document.getElementById('pay-coupon')||{}).value||'').trim();}
window.goMe=function(msg){
box(true,msg||'已开通');
try{if(typeof loadMe==='function')loadMe();}catch(e){}
try{if(typeof loadOrders==='function')loadOrders();}catch(e){}
try{if(typeof tab==='function')tab('me');}catch(e){}
};
function invoiceUrl(raw){
var u=String(raw||'').trim();
if(u.charAt(0)==='$') u='https://t.me/'+u;
if(u.indexOf('t.me/')===0) u='https://'+u;
return u;
}
async function postPay(path, extra){
var body=Object.assign({init_data:typeof initData!=='undefined'?initData:'',plan:_planId||'year',coupon:code()},extra||{});
var r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
var j={};try{j=await r.json();}catch(e){throw new Error('下单接口异常');}
if(!r.ok||j.error) throw new Error(j.error||('下单失败 '+r.status));
return j;
}
function showUsdt(u){
var c=document.getElementById('checkout');
if(c) c.classList.remove('hidden');
if(document.getElementById('oid')) document.getElementById('oid').textContent=u.code||'';
if(document.getElementById('oamt')) document.getElementById('oamt').textContent=(u.amount||'')+' USDT';
if(document.getElementById('ochain')) document.getElementById('ochain').textContent=(u.chain||'TRC20').toUpperCase();
if(document.getElementById('oaddr')) document.getElementById('oaddr').textContent=u.address||'';
window._addr=u.address||'';
box(true,(u.discount?('已优惠 '+u.discount+'% · '):'')+'请转账 '+(u.amount||'')+' USDT · '+(u.code||''));
try{if(typeof watchPaid==='function')watchPaid();}catch(e){}
}
function bind(){
var btns=document.querySelectorAll('#tab-pay button');
for(var i=0;i<btns.length;i++){
var b=btns[i];
b.setAttribute('type','button');
b.disabled=false;
var oc=b.getAttribute('onclick')||'';
var txt=b.textContent||'';
if(oc.indexOf("'stars'")>=0 || /Stars/.test(txt)){
b.textContent='Stars';
b.onclick=function(ev){if(ev)ev.preventDefault();window.pay(b,'stars');};
}else if(oc.indexOf("'usdt'")>=0 || /USDT/.test(txt)){
b.onclick=function(ev){if(ev)ev.preventDefault();window.pay(b,'usdt');};
}
}
}
window.pay=async function(btn,rail){
if(!user){box(false,'请从机器人打开');return;}
if(btn) btn.disabled=true;
try{
if(rail==='stars'){
var s=await postPay('/api/mini/pay-stars');
var inv=invoiceUrl(s.invoice);
if(!inv||!tg||!tg.openInvoice) throw new Error('当前客户端不能打开 Stars');
tg.openInvoice(inv,function(st){
if(st==='paid') window.goMe('支付成功，已开通');
else if(st==='cancelled') box(false,'已取消');
else if(st==='failed') box(false,'支付失败');
if(btn) btn.disabled=false;
});
return;
}
showUsdt(await postPay('/api/mini/pay-usdt'));
}catch(e){box(false,(e&&e.message)||'下单失败');}
if(btn) btn.disabled=false;
};
bind();
setTimeout(bind,400);
})();
</script></body>"""


def install_mini_html_middleware(app) -> None:
    @app.middleware("http")
    async def wave4_mini_html(request: Request, call_next):
        response = await call_next(request)
        if request.url.path != "/mini" or response.status_code != 200:
            return response
        try:
            body = b""
            async for chunk in response.body_iterator:
                body += chunk
            html = body.decode("utf-8", errors="replace")
            html = html.replace("?v=12", f"?v={MINI_ASSET_VER}")
            html = html.replace("?v=21", f"?v={MINI_ASSET_VER}")
            if "mini-card-api.js" not in html and 'src="/mini-core.js' in html:
                html = html.replace(
                    f'<script src="/mini-core.js?v={MINI_ASSET_VER}"></script>',
                    f'<script src="/mini-card-api.js?v={MINI_ASSET_VER}"></script>'
                    + f'<script src="/mini-core.js?v={MINI_ASSET_VER}"></script>',
                    1,
                )
            if "mini-ui.p0.js" not in html and 'src="/mini-ui.js' in html:
                parts = "".join(
                    f'<script src="/mini-ui.p{i}.js?v={MINI_ASSET_VER}"></script>'
                    for i in range(4)
                )
                html = html.replace(
                    f'<script src="/mini-ui.js?v={MINI_ASSET_VER}"></script>',
                    parts + f'<script src="/mini-ui.js?v={MINI_ASSET_VER}"></script>',
                    1,
                )
            html = patch_mini_html(html)
            extras = (
                "mini-confirm.js",
                "mini-onboard.js",
                "mini-pending.js",
                "mini-ops.js",
                "mini-invoice.js",
                "mini-coupon-fix.js",
                "mini-roles.js",
                "mini-reconcile.js",
                "mini-fx.js",
                "mini-reconcile-actions.js",
                "mini-ops-stars.js",
                "mini-saas.js",
                "mini-inline.js",
            )
            for name in extras:
                if name not in html:
                    html = html.replace(
                        "</body>",
                        f'<script src="/{name}?v={MINI_ASSET_VER}"></script></body>',
                    )
            if "__payBoot36=true" not in html:
                html = html.replace("</body>", _PAY_BOOT, 1)
            for late in ("mini-success.js", "mini-ref-admin.js", "mini-growth.js"):
                if late not in html:
                    html = html.replace(
                        "</body>",
                        f'<script src="/{late}?v={MINI_ASSET_VER}"></script></body>',
                    )
            return HTMLResponse(
                html,
                status_code=200,
                headers={
                    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                    "Pragma": "no-cache",
                },
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("wave4 mini html patch failed: %s", exc)
            return response
