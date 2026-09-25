/* wave9: Stars↔USDT admin FX rate + plan price convert */
(function () {
var _rate = 50;
var _live = false;

function qAuth() {
return (
'user_id=' +
((typeof user !== 'undefined' && user && user.id) || '') +
'&init_data=' +
encodeURIComponent(typeof initData !== 'undefined' ? initData : '')
);
}

function postJson(path, body) {
if (typeof api === 'function') return api(path, body || {});
body = Object.assign(
{
init_data: typeof initData !== 'undefined' ? initData : '',
user_id: (typeof user !== 'undefined' && user && user.id) || 0,
},
body || {}
);
return fetch(path, {
method: 'POST',
headers: { 'Content-Type': 'application/json' },
body: JSON.stringify(body),
}).then(function (r) {
return r.json().then(function (j) {
if (!r.ok || j.error) throw new Error(j.error || '请求失败');
return j;
});
});
}

function starsToUsdt(stars) {
var r = Number(_rate) || 50;
return Math.round((Math.max(0, Number(stars) || 0) / r) * 100) / 100;
}
function usdtToStars(usdt) {
var r = Number(_rate) || 50;
return Math.max(1, Math.round(Math.max(0, Number(usdt) || 0) * r));
}

function ensureFxPanel() {
var price = document.getElementById('asec-price');
if (!price || document.getElementById('fx-rate-card')) return;
var box = document.getElementById('aplanbox');
var card = document.createElement('div');
card.className = 'card';
card.id = 'fx-rate-card';
card.style.marginBottom = '12px';
card.innerHTML =
'<h2 class="sec">Stars ↔ USDT 汇率</h2>' +
'<p class="hint">管理员自设换算：1 USDT = N Stars。默认 50（非实时行情；仓库无既有汇率常量）。改价时可「按汇率换算」或开启自动换算。</p>' +
'<label>1 USDT = 多少 Stars</label>' +
'<input id="fx-rate" type="number" step="0.1" min="1" value="50" />' +
'<div class="btns">' +
'<button type="button" id="fx-save">保存汇率</button>' +
'<button type="button" class="ghost" id="fx-apply">按汇率换算全部套餐</button>' +
'<button type="button" class="ghost" id="fx-live">自动换算：关</button>' +
'</div>';
if (box && box.parentNode) box.parentNode.insertBefore(card, box);
else {
var host = price.querySelector('.card') || price;
host.insertBefore(card, host.firstChild);
}
document.getElementById('fx-save').onclick = saveFx;
document.getElementById('fx-apply').onclick = applyAll;
document.getElementById('fx-live').onclick = function () {
_live = !_live;
this.textContent = _live ? '自动换算：开' : '自动换算：关';
show(ok, _live ? '已开启：改 Stars/USDT 失焦时自动换算另一侧' : '已关闭自动换算');
};
loadFx();
}

async function loadFx() {
try {
var j = await fetch('/api/mini/admin/fx_rate?' + qAuth()).then(function (r) {
return r.json();
});
if (j.error) return;
_rate = Number(j.stars_per_usdt) || 50;
var inp = document.getElementById('fx-rate');
if (inp) inp.value = String(_rate);
} catch (e) {}
}

async function saveFx() {
try {
var v = Number((document.getElementById('fx-rate') || {}).value || 0);
var j = await postJson('/api/mini/admin/fx_rate', { stars_per_usdt: v });
_rate = Number(j.stars_per_usdt) || v;
show(ok, j.hint || ('已保存：1 USDT ≈ ' + _rate + ' Stars'));
} catch (e) {
show(err, e.message);
}
}

function readRateFromInput() {
var v = Number((document.getElementById('fx-rate') || {}).value || _rate);
if (v >= 1) _rate = v;
return _rate;
}

function convertCard(card, from) {
if (!card) return;
var sEl = card.querySelector('.pstars');
var uEl = card.querySelector('.pusdt');
if (!sEl || !uEl) return;
readRateFromInput();
if (from === 'stars') {
var s = Number(sEl.value || 0);
if (s > 0) uEl.value = String(starsToUsdt(s));
} else if (from === 'usdt') {
var u = Number(uEl.value || 0);
if (u > 0) sEl.value = String(usdtToStars(u));
}
}

function applyAll() {
readRateFromInput();
var box = document.getElementById('aplanbox');
if (!box) return;
var n = 0;
box.querySelectorAll('.plan-card').forEach(function (card) {
var sEl = card.querySelector('.pstars');
var uEl = card.querySelector('.pusdt');
if (!sEl || !uEl) return;
var s = Number(sEl.value || 0);
var u = Number(uEl.value || 0);
if (s > 0) {
uEl.value = String(starsToUsdt(s));
n++;
} else if (u > 0) {
sEl.value = String(usdtToStars(u));
n++;
}
});
show(ok, '已按汇率换算 ' + n + ' 个套餐（未点保存套餐前不会落库）');
}

function wirePlanInputs(box) {
if (!box) return;
box.querySelectorAll('.plan-card').forEach(function (card) {
if (card.getAttribute('data-fx') === '1') return;
card.setAttribute('data-fx', '1');
var sEl = card.querySelector('.pstars');
var uEl = card.querySelector('.pusdt');
var row = card.querySelector('.plan-row:last-of-type');
if (row && !card.querySelector('[data-fx-btn]')) {
var b1 = document.createElement('button');
b1.type = 'button';
b1.className = 'ghost';
b1.setAttribute('data-fx-btn', '1');
b1.textContent = '⭐→U';
b1.style.flex = '0 0 auto';
b1.onclick = function (ev) {
ev.preventDefault();
convertCard(card, 'stars');
};
var b2 = document.createElement('button');
b2.type = 'button';
b2.className = 'ghost';
b2.setAttribute('data-fx-btn', '1');
b2.textContent = 'U→⭐';
b2.style.flex = '0 0 auto';
b2.onclick = function (ev) {
ev.preventDefault();
convertCard(card, 'usdt');
};
var wrap = document.createElement('div');
wrap.className = 'btns';
wrap.style.marginTop = '8px';
wrap.appendChild(b1);
wrap.appendChild(b2);
card.appendChild(wrap);
}
function onBlurStars() {
if (_live) convertCard(card, 'stars');
}
function onBlurUsdt() {
if (_live) convertCard(card, 'usdt');
}
if (sEl) sEl.addEventListener('blur', onBlurStars);
if (uEl) uEl.addEventListener('blur', onBlurUsdt);
});
}

if (typeof renderAdminPlans === 'function') {
var _render = renderAdminPlans;
window.renderAdminPlans = function () {
_render.apply(this, arguments);
wirePlanInputs(document.getElementById('aplanbox'));
};
}

if (typeof loadAdmin === 'function') {
var _loadAdmin = loadAdmin;
window.loadAdmin = async function () {
await _loadAdmin.apply(this, arguments);
ensureFxPanel();
wirePlanInputs(document.getElementById('aplanbox'));
};
}

if (typeof tab === 'function') {
var _tab = tab;
window.tab = function (name) {
_tab.apply(this, arguments);
if (name === 'adm') {
ensureFxPanel();
wirePlanInputs(document.getElementById('aplanbox'));
}
};
}

function boot() {
ensureFxPanel();
wirePlanInputs(document.getElementById('aplanbox'));
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
else setTimeout(boot, 0);
})();
