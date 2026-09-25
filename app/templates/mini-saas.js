/* wave10: clone-bot instance list + enable/disable (SaaS MVP) */
(function () {
function qAuth() {
return (
'user_id=' +
((typeof user !== 'undefined' && user && user.id) || '') +
'&init_data=' +
encodeURIComponent(typeof initData !== 'undefined' ? initData : '')
);
}

function ensureSaasAdmin() {
var nav = document.getElementById('admnav');
var host = document.getElementById('tab-adm');
if (!nav || !host || document.getElementById('asec-clones')) return;

var btn = document.createElement('button');
btn.type = 'button';
btn.setAttribute('data-sec', 'clones');
btn.textContent = '克隆实例';
btn.onclick = function () {
if (typeof admSec === 'function') admSec('clones');
loadClones();
};
nav.appendChild(btn);

var sec = document.createElement('div');
sec.className = 'adm-sec';
sec.id = 'asec-clones';
sec.innerHTML =
'<div class="card"><h2 class="sec">克隆实例（白标）</h2>' +
'<p class="sub">已绑定 BotFather Token 的会员机器人。可查看会员档位/到期，启停 Webhook。不改租户模型，无经销商计费。</p>' +
'<p class="hint" id="cl-hint">打开本页加载</p>' +
'<div class="btns"><button type="button" id="cl-refresh">刷新列表</button></div>' +
'<div class="olist" id="cl-list">加载中…</div></div>';
var audit = document.getElementById('asec-audit');
if (audit) host.insertBefore(sec, audit);
else host.appendChild(sec);
document.getElementById('cl-refresh').onclick = loadClones;
}

async function loadClones() {
var el = document.getElementById('cl-list');
var hint = document.getElementById('cl-hint');
if (!el) return;
try {
var j = await fetch('/api/mini/admin/clones?' + qAuth()).then(function (r) {
return r.json();
});
if (j.error) {
el.textContent = j.error;
return;
}
if (hint) {
hint.textContent =
'全局克隆开关：' +
(j.clone_feature_on ? '开' : '关') +
' · 实例 ' +
(j.count || 0) +
' · Webhook 基址 ' +
(j.webhook_base || '（未配置 WEBHOOK_BASE_URL）');
}
var rows = j.clones || [];
if (!rows.length) {
el.textContent = '暂无已绑定的克隆机器人';
return;
}
el.innerHTML = rows
.map(function (c) {
var uname = c.bot_username ? '@' + c.bot_username : '（无用户名）';
var state = c.clone_enabled ? '运行中' : '已停用';
var mem =
(c.display_name || c.username || '—') +
' · ' +
(c.plan || '—') +
' · ' +
(c.paid_until_label || '—') +
(c.usable ? '' : ' · 会员失效');
return (
'<div data-tid="' +
c.tenant_id +
'">' +
'<b>' +
uname +
'</b> <span class="pill">' +
state +
'</span><br/>' +
'<span>租户 #' +
c.tenant_id +
' · 主人 TG ' +
c.owner_tg_id +
' · 状态 ' +
(c.status || '') +
'</span><br/>' +
'<span>' +
mem +
'</span><br/>' +
'<span class="mono" style="display:block;margin-top:6px;font-size:11px">' +
(c.webhook_url || '无 Webhook URL') +
'</span>' +
'<div class="btns" style="margin-top:8px">' +
(c.clone_enabled
? '<button type="button" class="ghost" data-act="disable">停用</button>'
: '<button type="button" data-act="enable">启用</button>') +
'<button type="button" class="ghost" data-act="webhook">Webhook 状态</button>' +
'</div></div>'
);
})
.join('');
el.querySelectorAll('[data-act]').forEach(function (b) {
b.onclick = function () {
var row = b.closest('[data-tid]');
var tid = row && row.getAttribute('data-tid');
doCloneAction(tid, b.getAttribute('data-act'));
};
});
} catch (e) {
el.textContent = (e && e.message) || String(e);
}
}

async function doCloneAction(tenantId, action) {
if (!tenantId || !action) return;
var label =
action === 'disable' ? '停用该克隆实例（删除 Webhook）？' : action === 'enable' ? '启用并重新设置 Webhook？' : null;
if (label && typeof confirmAct === 'function') {
var ok = await confirmAct(label);
if (!ok) return;
} else if (label && !window.confirm(label)) {
return;
}
try {
var body = {
action: action,
tenant_id: Number(tenantId),
init_data: typeof initData !== 'undefined' ? initData : '',
user_id: (typeof user !== 'undefined' && user && user.id) || 0,
};
var j = await fetch('/api/mini/admin/clones', {
method: 'POST',
headers: { 'Content-Type': 'application/json' },
body: JSON.stringify(body),
}).then(function (r) {
return r.json();
});
if (j.error) {
if (typeof show === 'function' && typeof err !== 'undefined') show(err, j.error);
else alert(j.error);
return;
}
if (action === 'webhook') {
var w = j.webhook || {};
var msg =
'期望：' +
(j.expected_url || '') +
'\n实际：' +
(w.url || '（空）') +
(w.last_error_message ? '\n错误：' + w.last_error_message : '') +
(w.pending_update_count != null ? '\n待处理：' + w.pending_update_count : '');
alert(msg);
} else if (typeof show === 'function' && typeof ok !== 'undefined') {
show(ok, j.message || '已保存');
}
loadClones();
} catch (e) {
if (typeof show === 'function' && typeof err !== 'undefined') show(err, e.message || String(e));
else alert(e.message || String(e));
}
}

function boot() {
ensureSaasAdmin();
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
else boot();
setTimeout(boot, 400);
})();
