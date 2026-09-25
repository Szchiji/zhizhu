/* wave9: row actions on top of mini-reconcile.js */
(function () {
function postJson(path, body) {
if (typeof api === 'function') return api(path, body || {});
body = Object.assign({
init_data: typeof initData !== 'undefined' ? initData : '',
user_id: (typeof user !== 'undefined' && user && user.id) || 0,
}, body || {});
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
function fillCode(code) {
var acode = document.getElementById('acode');
if (acode) acode.value = code;
var oq = document.getElementById('oq');
if (oq && code) oq.value = code;
}
function copyText(text) {
text = String(text || '');
if (!text) return Promise.reject(new Error('空'));
if (navigator.clipboard && navigator.clipboard.writeText) return navigator.clipboard.writeText(text);
return new Promise(function (resolve, reject) {
var ta = document.createElement('textarea');
ta.value = text;
document.body.appendChild(ta);
ta.select();
try { document.execCommand('copy'); resolve(); }
catch (e) { reject(e); }
finally { document.body.removeChild(ta); }
});
}
async function confirmRow(code) {
var yes = true;
if (typeof confirmAct === 'function') yes = await confirmAct('确认开通', '手动确认 ' + code + ' 将立即开通会员，确认？');
else yes = window.confirm('确认开通 ' + code + '？');
if (!yes) return;
try {
fillCode(code);
var j = await postJson('/api/mini/admin', { action: 'confirm', code: code, txid: '' });
show(ok, j.message || ('已确认 ' + code));
if (typeof loadReconcile === 'function') loadReconcile();
} catch (e) { show(err, e.message); }
}
async function revokeRow(code) {
var yes = true;
if (typeof confirmAct === 'function') {
yes = await confirmAct('撤销开通', '撤销 ' + code + '：回退会员天数；若为 Stars 且有 charge_id 将尝试官方退款。确认？');
} else yes = window.confirm('撤销 ' + code + '？');
if (!yes) return;
try {
fillCode(code);
var j = await postJson('/api/mini/admin/revoke', { code: code });
var msg = j.message || ('已撤销 ' + (j.code || code));
var sr = j.stars_refund;
if (sr && sr.attempted && !sr.ok) msg += '（官方退款失败：' + (sr.description || sr.error || '') + '）';
show(ok, msg);
if (typeof loadReconcile === 'function') loadReconcile();
if (typeof searchOrders === 'function') searchOrders();
} catch (e) { show(err, e.message); }
}
function openDetail(code) {
fillCode(code);
if (typeof admSec === 'function') admSec('orders');
if (typeof searchOrders === 'function') try { searchOrders(); } catch (e) {}
show(ok, '已打开订单详情：' + code);
}
function enhanceList() {
var el = document.getElementById('rc-list');
if (!el) return;
el.querySelectorAll('.rc-row').forEach(function (row) {
if (row.getAttribute('data-act') === '1') return;
row.setAttribute('data-act', '1');
var code = row.getAttribute('data-c') || '';
var bar = document.createElement('div');
bar.className = 'btns';
bar.style.marginTop = '8px';
function mk(label, act, ghost) {
var b = document.createElement('button');
b.type = 'button';
if (ghost) b.className = 'ghost';
b.textContent = label;
b.onclick = function (ev) {
ev.stopPropagation();
if (act === 'confirm') confirmRow(code);
else if (act === 'revoke') revokeRow(code);
else if (act === 'copy') copyText(code).then(function () { show(ok, '已复制 ' + code); }).catch(function () { show(err, '复制失败'); });
else if (act === 'detail') openDetail(code);
};
return b;
}
bar.appendChild(mk('确认开通', 'confirm', false));
bar.appendChild(mk('撤销', 'revoke', true));
bar.appendChild(mk('复制单号', 'copy', true));
bar.appendChild(mk('打开详情', 'detail', true));
row.appendChild(bar);
});
}
if (typeof loadReconcile === 'function') {
var _lr = loadReconcile;
window.loadReconcile = async function () {
await _lr.apply(this, arguments);
enhanceList();
};
}
var obs = new MutationObserver(function () { enhanceList(); });
function boot() {
var el = document.getElementById('rc-list');
if (el) obs.observe(el, { childList: true, subtree: true });
enhanceList();
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
else setTimeout(boot, 0);
})();
