/* Sync card templates into hidden textareas AND visible editors. */
function _fillVisFromTa() {
  ['ctpaid', 'ctunpaid', 'ctissuer'].forEach(function (id) {
    var ta = document.getElementById(id);
    var vis = document.getElementById(id + '-vis');
    if (!ta || !vis) return;
    var v = ta.value || '';
    if (vis.innerText.trim() === v.trim()) return;
    vis.textContent = v;
  });
}
function _schedulePaint() {
  _fillVisFromTa();
  if (typeof window.paintAllVisFromTa === 'function') {
    try { window.paintAllVisFromTa(); } catch (e) {}
  }
  [300, 800, 1600, 2800].forEach(function (ms) {
    setTimeout(_fillVisFromTa, ms);
  });
}
async function _loadCardTplFallback() {
  try {
    var uid = (typeof user !== 'undefined' && user && user.id) || '';
    var idata = typeof initData !== 'undefined' ? initData : '';
    var j = await fetch(
      '/api/mini/admin/card?user_id=' + uid + '&init_data=' + encodeURIComponent(idata)
    ).then(function (r) { return r.json(); });
    if (j.error || !j.card_tpl) return;
    var t = j.card_tpl;
    var paid = document.getElementById('ctpaid');
    var unpaid = document.getElementById('ctunpaid');
    var issuer = document.getElementById('ctissuer');
    if (paid) paid.value = t.paid || '';
    if (unpaid) unpaid.value = t.unpaid || '';
    if (issuer) issuer.value = t.issuer || '';
    var btn = document.getElementById('btnsavecard');
    if (btn) btn.disabled = false;
    _schedulePaint();
  } catch (e) {}
}
async function loadCardTpl() {
  return _loadCardTplFallback();
}
function _visEmptyButTaFilled() {
  return ['ctpaid', 'ctunpaid', 'ctissuer'].every(function (id) {
    var vis = document.getElementById(id + '-vis');
    var ta = document.getElementById(id);
    return ta && ta.value.trim() && vis && !vis.innerText.trim();
  });
}
async function saveCardTpl() {
  try {
    if (!_visEmptyButTaFilled() && typeof window.syncVisToTa === 'function') {
      try { window.syncVisToTa(); } catch (e) {}
    }
    var paid = (document.getElementById('ctpaid') || {}).value || '';
    var unpaid = (document.getElementById('ctunpaid') || {}).value || '';
    var issuer = (document.getElementById('ctissuer') || {}).value || '';
    if (!paid.trim() && !unpaid.trim() && !issuer.trim()) {
      throw new Error('模板还是空的，没有写入。请先点「标准包」再保存');
    }
    if (typeof api !== 'function') throw new Error('管理脚本尚未就绪');
    await api('/api/mini/admin/card', { paid: paid, unpaid: unpaid, issuer: issuer });
    var btn = document.getElementById('btnsavecard');
    if (btn) btn.disabled = false;
    _schedulePaint();
    if (typeof show === 'function' && typeof ok !== 'undefined') {
      show(ok, '卡片模板已保存。请重新查询一张卡核对');
    }
  } catch (e) {
    if (typeof show === 'function' && typeof err !== 'undefined') show(err, e.message || String(e));
  }
}
async function cardPack(pack) {
  try {
    var j = await api('/api/mini/admin/card', { apply_pack: true, pack: pack });
    var t = j.card_tpl || {};
    if (document.getElementById('ctpaid')) document.getElementById('ctpaid').value = t.paid || '';
    if (document.getElementById('ctunpaid')) document.getElementById('ctunpaid').value = t.unpaid || '';
    if (document.getElementById('ctissuer')) document.getElementById('ctissuer').value = t.issuer || '';
    _schedulePaint();
    if (typeof show === 'function' && typeof ok !== 'undefined') {
      show(ok, '已写入版式预设，请再点保存模板');
    }
  } catch (e) {
    if (typeof show === 'function' && typeof err !== 'undefined') show(err, e.message || String(e));
  }
}
function previewTpl(id) {
  var src = document.getElementById(id);
  var box = document.getElementById('card-preview');
  var body = document.getElementById('card-preview-body');
  if (!src || !box || !body) return;
  box.classList.remove('hidden');
  body.textContent = src.value || '(空模板)';
}
