/* Inline list title/description templates — subsection under 卡片模板 */
(function () {
  var KINDS = [
    { key: 'paid', label: '已登记' },
    { key: 'unpaid', label: '未登记' },
    { key: 'issuer', label: '出具方' },
    { key: 'clone', label: '克隆机' },
  ];
  var PH = ['{品牌}', '{机器人}', '{姓名}', '{账号}', '{ID}', '{查询词}', '{有效期}'];
  var _loaded = false;

  function qAuth() {
    return (
      'user_id=' +
      ((typeof user !== 'undefined' && user && user.id) || '') +
      '&init_data=' +
      encodeURIComponent(typeof initData !== 'undefined' ? initData : '')
    );
  }

  function ensureInlineTplUi() {
    var card = document.getElementById('asec-card');
    if (!card || document.getElementById('inline-tpl-box')) return;
    var host = card.querySelector('.card') || card;
    var box = document.createElement('div');
    box.id = 'inline-tpl-box';
    box.innerHTML =
      '<div class="divider"></div>' +
      '<h2 class="sec">内联列表标题</h2>' +
      '<p class="sub">Inline 标题与副标题（纯文本，无 HTML）。占位符：' +
      PH.join(' ') +
      '。空查询未登记仍用默认「品牌·平台登记 / 输入用户名查询」。</p>' +
      KINDS.map(function (k) {
        return (
          '<label>' +
          k.label +
          ' · 标题</label>' +
          '<input id="it-' +
          k.key +
          '-title" maxlength="64" placeholder="标题" />' +
          '<label>' +
          k.label +
          ' · 副标题</label>' +
          '<input id="it-' +
          k.key +
          '-desc" maxlength="100" placeholder="副标题" />'
        );
      }).join('') +
      '<p class="hint">占位符提示：{账号} 含 @；{查询词} 为用户名（无 @）。标题约 64 字、副标题约 100 字，超长自动截断。</p>' +
      '<div class="btns"><button type="button" id="btnsaveinline" disabled>保存内联标题</button></div>';
    host.appendChild(box);
    var btn = document.getElementById('btnsaveinline');
    if (btn) btn.onclick = saveInlineTpl;
    loadInlineTpl();
  }

  async function loadInlineTpl() {
    var btn = document.getElementById('btnsaveinline');
    if (btn) btn.disabled = true;
    _loaded = false;
    try {
      var j = await fetch('/api/mini/admin/inline_tpl?' + qAuth()).then(function (r) {
        return r.json();
      });
      if (j.error || !j.inline_tpl) return;
      var t = j.inline_tpl;
      KINDS.forEach(function (k) {
        var row = t[k.key] || {};
        var ti = document.getElementById('it-' + k.key + '-title');
        var di = document.getElementById('it-' + k.key + '-desc');
        if (ti) ti.value = row.title || '';
        if (di) di.value = row.description || '';
      });
      _loaded = true;
      if (btn) btn.disabled = false;
    } catch (e) {}
  }

  async function saveInlineTpl() {
    if (!_loaded) {
      if (typeof show === 'function' && typeof err !== 'undefined') show(err, '内联模板尚未加载完成');
      return;
    }
    var payload = { inline_tpl: {} };
    KINDS.forEach(function (k) {
      var ti = document.getElementById('it-' + k.key + '-title');
      var di = document.getElementById('it-' + k.key + '-desc');
      payload.inline_tpl[k.key] = {
        title: ti ? ti.value : '',
        description: di ? di.value : '',
      };
    });
    try {
      var j;
      if (typeof api === 'function') {
        j = await api('/api/mini/admin/inline_tpl', payload);
      } else {
        j = await fetch('/api/mini/admin/inline_tpl', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(
            Object.assign({}, payload, {
              init_data: typeof initData !== 'undefined' ? initData : '',
            })
          ),
        }).then(function (r) {
          return r.json();
        });
      }
      if (j.error) throw new Error(j.error);
      var t = j.inline_tpl || {};
      KINDS.forEach(function (k) {
        var row = t[k.key] || {};
        var ti = document.getElementById('it-' + k.key + '-title');
        var di = document.getElementById('it-' + k.key + '-desc');
        if (ti && row.title != null) ti.value = row.title;
        if (di && row.description != null) di.value = row.description;
      });
      if (typeof show === 'function' && typeof ok !== 'undefined')
        show(ok, '内联标题已保存。请重新发起一次 Inline 查询核对；列表缓存不会自动刷新。');
    } catch (e) {
      if (typeof show === 'function' && typeof err !== 'undefined') show(err, e.message || String(e));
    }
  }

  function boot() {
    ensureInlineTplUi();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
  // Re-try after card tab may load late
  setTimeout(ensureInlineTplUi, 800);
  window.loadInlineTpl = loadInlineTpl;
  window.saveInlineTpl = saveInlineTpl;
})();
