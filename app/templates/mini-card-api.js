/* Fallback card-template API. Defined synchronously so loadAdmin never hits a missing loadCardTpl. */
async function _loadCardTplFallback() {
  try {
    const uid = (typeof user !== 'undefined' && user && user.id) || '';
    const idata = typeof initData !== 'undefined' ? initData : '';
    const j = await fetch(
      '/api/mini/admin/card?user_id=' + uid + '&init_data=' + encodeURIComponent(idata)
    ).then((r) => r.json());
    if (j.error || !j.card_tpl) return;
    const t = j.card_tpl;
    const paid = document.getElementById('ctpaid');
    const unpaid = document.getElementById('ctunpaid');
    const issuer = document.getElementById('ctissuer');
    if (paid) paid.value = t.paid || '';
    if (unpaid) unpaid.value = t.unpaid || '';
    if (issuer) issuer.value = t.issuer || '';
    const btn = document.getElementById('btnsavecard');
    if (btn) btn.disabled = false;
    if (typeof window.paintAllVisFromTa === 'function') {
      try { window.paintAllVisFromTa(); } catch (e) {}
    }
  } catch (e) {}
}
async function loadCardTpl() {
  return _loadCardTplFallback();
}
async function saveCardTpl() {
  try {
    if (typeof window.syncVisToTa === 'function') {
      try { window.syncVisToTa(); } catch (e) {}
    }
    const paid = (document.getElementById('ctpaid') || {}).value || '';
    const unpaid = (document.getElementById('ctunpaid') || {}).value || '';
    const issuer = (document.getElementById('ctissuer') || {}).value || '';
    if (typeof api === 'function') {
      await api('/api/mini/admin/card', { paid: paid, unpaid: unpaid, issuer: issuer });
    } else {
      throw new Error('管理脚本尚未就绪');
    }
    const btn = document.getElementById('btnsavecard');
    if (btn) btn.disabled = false;
    if (typeof show === 'function' && typeof ok !== 'undefined') {
      show(ok, '卡片模板已保存。请重新查询一张卡核对，旧卡不会自动换文案');
    }
  } catch (e) {
    if (typeof show === 'function' && typeof err !== 'undefined') show(err, e.message || String(e));
  }
}
async function cardPack(pack) {
  try {
    const j = await api('/api/mini/admin/card', { apply_pack: true, pack: pack });
    const t = j.card_tpl || {};
    if (document.getElementById('ctpaid')) document.getElementById('ctpaid').value = t.paid || '';
    if (document.getElementById('ctunpaid')) document.getElementById('ctunpaid').value = t.unpaid || '';
    if (document.getElementById('ctissuer')) document.getElementById('ctissuer').value = t.issuer || '';
    if (typeof window.paintAllVisFromTa === 'function') {
      try { window.paintAllVisFromTa(); } catch (e) {}
    }
    if (typeof show === 'function' && typeof ok !== 'undefined') show(ok, '已套用格式包，请再点保存模板');
  } catch (e) {
    if (typeof show === 'function' && typeof err !== 'undefined') show(err, e.message || String(e));
  }
}
function previewTpl(id) {
  const src = document.getElementById(id);
  const box = document.getElementById('card-preview');
  const body = document.getElementById('card-preview-body');
  if (!src || !box || !body) return;
  box.classList.remove('hidden');
  body.textContent = src.value || '(空模板)';
}
