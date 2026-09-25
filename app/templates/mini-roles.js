/* wave8: roles admin UI + capability nav gate */
(function () {
var ROLE_CAPS = {
owner: ['*'],
ops: [
'view', 'confirm', 'price', 'users', 'export', 'channel', 'remind',
'home', 'card', 'clone', 'coupon', 'revoke', 'reconcile',
],
support: ['view', 'confirm'],
};
var SEC_CAP = {
price: 'price',
card: 'card',
home: 'home',
users: 'users',
orders: 'confirm',
channel: 'channel',
audit: 'view',
coupons: 'coupon',
roles: 'view',
reconcile: 'reconcile',
};
var ROLE_LABEL = { owner: '所有者', ops: '运营', support: '客服' };
var _meRole = '';
var _roleMap = {};

function qAuth() {
return (
'user_id=' +
((typeof user !== 'undefined' && user && user.id) || '') +
'&init_data=' +
encodeURIComponent(typeof initData !== 'undefined' ? initData : '')
);
}

async function postJson(path, body) {
if (typeof api === 'function') return api(path, body || {});
body = Object.assign(
{
init_data: typeof initData !== 'undefined' ? initData : '',
user_id: (typeof user !== 'undefined' && user && user.id) || 0,
},
body || {}
);
var r = await fetch(path, {
method: 'POST',
headers: { 'Content-Type': 'application/json' },
body: JSON.stringify(body),
});
var j = await r.json();
if (!r.ok || j.error) throw new Error(j.error || '请求失败');
return j;
}

function hasCap(role, cap) {
var caps = ROLE_CAPS[role] || [];
return caps.indexOf('*') >= 0 || caps.indexOf(cap) >= 0;
}

function gateAdminNav() {
if (!_meRole) return;
document.querySelectorAll('#admnav button').forEach(function (btn) {
var sec = btn.getAttribute('data-sec') || '';
var need = SEC_CAP[sec] || 'view';
btn.style.display = hasCap(_meRole, need) ? '' : 'none';
});
var revoke = document.getElementById('abtn-revoke');
if (revoke) revoke.style.display = hasCap(_meRole, 'revoke') ? '' : 'none';
var cpSave = document.getElementById('cp-save');
if (cpSave) cpSave.style.display = hasCap(_meRole, 'coupon') ? '' : 'none';
}

function ensureRolesAdmin() {
var nav = document.getElementById('admnav');
var host = document.getElementById('tab-adm');
if (!nav || !host || document.getElementById('asec-roles')) return;

var btn = document.createElement('button');
btn.type = 'button';
btn.setAttribute('data-sec', 'roles');
btn.textContent = '角色';
btn.onclick = function () {
if (typeof admSec === 'function') admSec('roles');
loadRoles();
};
nav.appendChild(btn);

var sec = document.createElement('div');
sec.className = 'adm-sec';
sec.id = 'asec-roles';
sec.innerHTML =
'<div class="card"><h2 class="sec">管理角色</h2>' +
'<p class="sub" id="roles-me">当前角色：—</p>' +
'<p class="hint">所有者可指派运营/客服。环境变量里的管理员默认视为所有者。</p>' +
'<div class="olist" id="roles-list">打开本页自动加载</div>' +
'<div id="roles-edit">' +
'<label>电报 ID</label><input id="role-tg" placeholder="数字 ID" />' +
'<label>角色</label><select id="role-sel">' +
'<option value="ops">运营</option>' +
'<option value="support">客服</option>' +
'<option value="owner">所有者</option>' +
'</select>' +
'<div class="btns"><button type="button" id="role-save">保存角色</button>' +
'<button type="button" class="ghost" id="role-refresh">刷新</button></div>' +
'</div></div>';
var audit = document.getElementById('asec-audit');
if (audit) host.insertBefore(sec, audit);
else host.appendChild(sec);
document.getElementById('role-save').onclick = saveRole;
document.getElementById('role-refresh').onclick = loadRoles;
}

async function loadRoles() {
var el = document.getElementById('roles-list');
var meEl = document.getElementById('roles-me');
if (!el) return;
try {
var j = await fetch('/api/mini/admin/roles?' + qAuth()).then(function (r) {
return r.json();
});
if (j.error) {
el.textContent = j.error;
return;
}
_meRole = j.me_role || _meRole || '';
_roleMap = j.roles || {};
if (meEl) {
meEl.textContent =
'当前角色：' +
(ROLE_LABEL[_meRole] || _meRole || '无') +
(j.env_admins && j.env_admins.length
? ' · 环境管理员 ' + j.env_admins.join(',')
: '');
}
var edit = document.getElementById('roles-edit');
if (edit) edit.style.display = hasCap(_meRole, '*') ? '' : 'none';
var keys = Object.keys(_roleMap).sort();
if (!keys.length) {
el.textContent = '暂无角色映射';
gateAdminNav();
return;
}
el.innerHTML = keys
.map(function (tid) {
var r = _roleMap[tid];
var canEdit = hasCap(_meRole, '*');
return (
'<div><b>' +
tid +
'</b> · ' +
(ROLE_LABEL[r] || r) +
(canEdit
? ' <button type="button" class="ghost role-rm" data-tg="' +
tid +
'" style="flex:0;padding:4px 10px;margin-left:6px">移除</button>'
: '') +
'</div>'
);
})
.join('');
el.querySelectorAll('.role-rm').forEach(function (b) {
b.onclick = function () {
removeRole(b.getAttribute('data-tg'));
};
});
gateAdminNav();
} catch (e) {
el.textContent = e.message || '加载失败';
}
}

async function saveRole() {
if (!hasCap(_meRole, '*')) {
show(err, '仅所有者可改角色');
return;
}
var tid = (document.getElementById('role-tg').value || '').trim();
var role = (document.getElementById('role-sel').value || '').trim();
if (!/^\d+$/.test(tid)) {
show(err, '请填写数字电报 ID');
return;
}
var next = Object.assign({}, _roleMap);
next[tid] = role;
try {
var yes = true;
if (typeof confirmAct === 'function') {
yes = await confirmAct(
'保存角色',
'将 ' + tid + ' 设为「' + (ROLE_LABEL[role] || role) + '」，确认？'
);
}
if (!yes) return;
var j = await postJson('/api/mini/admin/roles', { roles: next });
show(ok, '角色已保存');
_roleMap = j.roles || next;
loadRoles();
} catch (e) {
show(err, e.message);
}
}

async function removeRole(tid) {
if (!hasCap(_meRole, '*')) return;
var yes = true;
if (typeof confirmAct === 'function') {
yes = await confirmAct('移除角色', '移除 ' + tid + ' 的角色指派？');
} else {
yes = window.confirm('移除 ' + tid + '？');
}
if (!yes) return;
var next = Object.assign({}, _roleMap);
delete next[tid];
try {
await postJson('/api/mini/admin/roles', { roles: next });
show(ok, '已移除 ' + tid);
loadRoles();
} catch (e) {
show(err, e.message);
}
}

function captureMeRole(j) {
if (j && j.admin_role) _meRole = j.admin_role;
else if (j && j.is_admin && !_meRole) _meRole = 'owner';
gateAdminNav();
}

if (typeof loadAdmin === 'function') {
var _loadAdmin = loadAdmin;
window.loadAdmin = async function () {
await _loadAdmin.apply(this, arguments);
ensureRolesAdmin();
if (!_meRole) {
try {
var j = await fetch('/api/mini/admin/roles?' + qAuth()).then(function (r) {
return r.json();
});
if (!j.error) {
_meRole = j.me_role || '';
_roleMap = j.roles || {};
}
} catch (e) {}
}
gateAdminNav();
};
}

if (typeof tab === 'function') {
var _tab = tab;
window.tab = function (name) {
_tab.apply(this, arguments);
if (name === 'adm') {
ensureRolesAdmin();
gateAdminNav();
}
};
}

(function patchMeFetch() {
if (window.__vh_me_patched) return;
window.__vh_me_patched = true;
var _fetch = window.fetch;
window.fetch = function (input, init) {
var url = typeof input === 'string' ? input : (input && input.url) || '';
return _fetch.apply(this, arguments).then(function (resp) {
if (url.indexOf('/api/mini/me') >= 0) {
resp
.clone()
.json()
.then(function (j) {
captureMeRole(j);
})
.catch(function () {});
}
return resp;
});
};
})();

function boot() {
ensureRolesAdmin();
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
else setTimeout(boot, 0);
})();
