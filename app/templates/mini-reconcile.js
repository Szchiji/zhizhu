/* wave8: USDT reconcile / payment-review admin UI */
(function () {
var FLAG_LABEL = {
expired_unpaid: '过期未付',
active_without_txid: '已开通无哈希',
txid_but_not_active: '有哈希未开通',
expired: '已过期',
};
var _flagOnly = true;

function qAuth() {
return (
'user_id=' +
((typeof user !== 'undefined' && user && user.id) || '') +
'&init_data=' +
encodeURIComponent(typeof initData !== 'undefined' ? initData : '')
);
}

function ensureReconcileAdmin() {
var nav = document.getElementById('admnav');
var host = document.getElementById('tab-adm');
if (!nav || !host || document.getElementById('asec-reconcile')) return;

var btn = document.createElement('button');
btn.type = 'button';
btn.setAttribute('data-sec', 'reconcile');
btn.textContent = '对账';
btn.onclick = function () {
if (typeof admSec === 'function') admSec('reconcile');
loadReconcile();
};
nav.appendChild(btn);

var sec = document.createElement('div');
sec.className = 'adm-sec';
sec.id = 'asec-reconcile';
sec.innerHTML =
'<div class="card"><h2 class="sec">USDT 对账</h2>' +
'<p class="sub">只读核对：过期未付、有哈希未开通、已开通无哈希等异常单。点选可填入订单号以便确认/撤销。</p>' +
'<div class="btns">' +
'<button type="button" id="rc-refresh">刷新对账</button>' +
'<button type="button" class="ghost" id="rc-flag">仅异常：开</button>' +
'</div>' +
'<div class="olist" id="rc-list">打开本页自动加载</div></div>';
var orders = document.getElementById('asec-orders');
if (orders && orders.nextSibling) host.insertBefore(sec, orders.nextSibling);
else {
var audit = document.getElementById('asec-audit');
if (audit) host.insertBefore(sec, audit);
else host.appendChild(sec);
}
document.getElementById('rc-refresh').onclick = loadReconcile;
document.getElementById('rc-flag').onclick = function () {
_flagOnly = !_flagOnly;
this.textContent = _flagOnly ? '仅异常：开' : '仅异常：关';
loadReconcile();
};
}

async function loadReconcile() {
var el = document.getElementById('rc-list');
if (!el) return;
try {
var j = await fetch('/api/mini/admin/reconcile?limit=80&' + qAuth()).then(function (r) {
return r.json();
});
if (j.error) {
el.textContent = j.error;
return;
}
var rows = j.orders || [];
if (_flagOnly) rows = rows.filter(function (o) { return !!o.flag; });
if (!rows.length) {
el.textContent = _flagOnly ? '暂无异常单' : '暂无 USDT 订单';
return;
}
el.innerHTML = rows
.map(function (o) {
var flag = o.flag ? FLAG_LABEL[o.flag] || o.flag : '正常';
return (
'<div class="rc-row" data-c="' +
(o.code || '') +
'"><b>' +
(o.code || '') +
'</b> · ' +
(o.amount || '') +
'U · ' +
(o.status || '') +
(o.tg_id ? ' · TG ' + o.tg_id : '') +
'<br><span>' +
flag +
(o.txid ? ' · tx ' + String(o.txid).slice(0, 12) + '…' : '') +
(o.expires_at ? ' · 截止 ' + o.expires_at : '') +
'</span></div>'
);
})
.join('');
el.querySelectorAll('.rc-row').forEach(function (row) {
row.onclick = function () {
var code = row.getAttribute('data-c') || '';
var acode = document.getElementById('acode');
if (acode) acode.value = code;
var oq = document.getElementById('oq');
if (oq && code) oq.value = code;
show(ok, '已填入订单 ' + code + '（可到「订单」确认或撤销）');
};
});
} catch (e) {
el.textContent = e.message || '加载失败';
}
}

if (typeof loadAdmin === 'function') {
var _loadAdmin = loadAdmin;
window.loadAdmin = async function () {
await _loadAdmin.apply(this, arguments);
ensureReconcileAdmin();
};
}

if (typeof tab === 'function') {
var _tab = tab;
window.tab = function (name) {
_tab.apply(this, arguments);
if (name === 'adm') ensureReconcileAdmin();
};
}

function boot() {
ensureReconcileAdmin();
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
else setTimeout(boot, 0);
})();
