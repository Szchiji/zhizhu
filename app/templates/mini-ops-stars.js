/* wave9: update revoke confirm copy for Stars official refund */
(function () {
if (typeof revokeOrder !== 'function') return;
var _rev = revokeOrder;
window.revokeOrder = async function () {
var code = ((document.getElementById('acode') || {}).value || '').trim();
if (!code) { show(err, '请填写订单号'); return; }
var yes = true;
if (typeof confirmAct === 'function') {
yes = await confirmAct('撤销开通', '撤销 ' + code + ' 将回退会员天数；Stars 订单若有 charge_id 会尝试官方退款。确认？');
} else yes = window.confirm('撤销 ' + code + '？');
if (!yes) return;
try {
var body = {
init_data: typeof initData !== 'undefined' ? initData : '',
user_id: (typeof user !== 'undefined' && user && user.id) || 0,
code: code,
};
var j;
if (typeof api === 'function') j = await api('/api/mini/admin/revoke', { code: code });
else {
var r = await fetch('/api/mini/admin/revoke', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
j = await r.json();
if (!r.ok || j.error) throw new Error(j.error || '请求失败');
}
var msg = j.message || ('已撤销 ' + (j.code || code) + (j.paid_until ? ' · 到期 ' + j.paid_until : ''));
var sr = j.stars_refund;
if (sr && sr.attempted && !sr.ok) msg += '（官方退款失败：' + (sr.description || sr.error || '') + '）';
show(ok, msg);
if (typeof searchOrders === 'function') searchOrders();
} catch (e) { show(err, e.message); }
};
})();
