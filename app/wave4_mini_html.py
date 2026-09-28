"""Wave4: /mini HTML cache-bust + confirm script inject middleware."""
from __future__ import annotations

import logging

from fastapi import Request
from fastapi.responses import HTMLResponse

from app.static_ver import MINI_ASSET_VER
from app.wave_card_wysiwyg import patch_mini_html

log = logging.getLogger("zhizhu.wave4_mini")

_PAY_BOOT = r"""<script>
window.__payBoot32=true;
window.__couponPayWrap=true;
(function(){
function box(ok,msg){
var t=String(msg||'');
if(/expected pattern/i.test(t)) t=ok?'下单已提交':'USDT 下单失败，请清空折扣码再试';
var a=document.getElementById(ok?'ok':'err');
if(a){a.style.display='block';a.textContent=t;}
var b=document.getElementById(ok?'err':'ok');
if(b) b.style.display='none';
var h=document.getElementById('pay-coupon-hint');
if(h) h.textContent=t;
}
function code(){return ((document.getElementById('pay-coupon')||{}).value||'').trim();}
async function postUsdt(coupon){
var r=await fetch('/api/mini/pay-usdt',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({init_data:typeof initData!=='undefined'?initData:'',plan:_planId||'year',coupon:coupon||''})});
var j={};
try{j=await r.json();}catch(e){throw new Error('USDT 接口无法解读');}
if(!r.ok||j.error) throw new Error(j.error||('USDT '+r.status));
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
box(true,'请转账 '+(u.amount||'')+' USDT，订单 '+(u.code||''));
}
function lockStars(){
var btns=document.querySelectorAll('#tab-pay button');
for(var i=0;i<btns.length;i++){
var b=btns[i];
b.setAttribute('type','button');
var oc=b.getAttribute('onclick')||'';
if(oc.indexOf("'stars'")>=0 || (b.textContent||'').indexOf('Stars')>=0){
b.disabled=true;b.textContent='暂不可用 Stars';
b.onclick=function(ev){if(ev)ev.preventDefault();box(false,'请点绿色 USDT');};
}else if(oc.indexOf("'usdt'")>=0 || (b.textContent||'').indexOf('USDT')>=0){
b.onclick=function(ev){if(ev)ev.preventDefault();window.pay(b,'usdt');};
}
}
var inputs=document.querySelectorAll('input,textarea');
for(var j=0;j<inputs.length;j++) inputs[j].removeAttribute('pattern');
}
window.pay=async function(btn,rail){
if(rail==='stars'){box(false,'请点绿色 USDT');return;}
if(!user){box(false,'请从机器人打开');return;}
if(btn) btn.disabled=true;
try{
var u;
try{u=await postUsdt(code());}
catch(e1){u=await postUsdt('');}
showUsdt(u);
}catch(e){box(false,(e&&e.message)||'USDT 下单失败');}
if(btn) btn.disabled=false;
};
lockStars();
setTimeout(lockStars,300);
setTimeout(lockStars,1000);
var err=document.getElementById('err');
if(err&&/expected pattern/i.test(err.textContent||'')) err.style.display='none';
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
            if "__payBoot32=true" not in html:
                html = html.replace("</body>", _PAY_BOOT, 1)
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
