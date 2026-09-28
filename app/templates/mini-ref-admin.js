(function () {
  function box(ok, msg) {
    var a = document.getElementById(ok ? 'ok' : 'err');
    if (a) {
      a.style.display = 'block';
      a.textContent = String(msg || '');
    }
  }
  function ensure() {
    var host = document.getElementById('asec-price');
    if (!host || document.getElementById('ref-admin')) return;
    var card = host.querySelector('.card') || host;
    var wrap = document.createElement('div');
    wrap.id = 'ref-admin';
    wrap.innerHTML =
      '<div class="divider"></div>' +
      '<h2 class="sec">邀请奖励</h2>' +
      '<p class="hint">好友从邀请链接进来并首次开通，邀请人叠加天数。</p>' +
      '<label>奖励天数</label>' +
      '<input id="ref-days" type="number" min="1" max="365" value="7" />' +
      '<div class="btns">' +
      '<button type="button" class="ghost" id="ref-save">保存邀请</button>' +
      '<button type="button" class="ghost" id="ref-toggle">邀请：开</button>' +
      '</div>';
    card.appendChild(wrap);
    document.getElementById('ref-save').onclick = save;
    document.getElementById('ref-toggle').onclick = function () {
      window._refOn = !window._refOn;
      document.getElementById('ref-toggle').textContent = window._refOn ? '邀请：开' : '邀请：关';
      save();
    };
    load();
  }
  async function load() {
    try {
      var r = await fetch(
        '/api/mini/referral?init_data=' + encodeURIComponent(typeof initData !== 'undefined' ? initData : '')
      ).then(function (x) {
        return x.json();
      });
      window._refOn = !!r.on;
      if (document.getElementById('ref-days')) document.getElementById('ref-days').value = r.days || 7;
      if (document.getElementById('ref-toggle')) {
        document.getElementById('ref-toggle').textContent = window._refOn ? '邀请：开' : '邀请：关';
      }
    } catch (e) {}
  }
  async function save() {
    try {
      var r = await fetch('/api/mini/admin/referral', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          init_data: typeof initData !== 'undefined' ? initData : '',
          on: !!window._refOn,
          days: (document.getElementById('ref-days') || {}).value || 7,
        }),
      });
      var j = await r.json();
      if (!r.ok || j.error) throw new Error(j.error || '保存失败');
      window._refOn = !!j.on;
      box(true, '邀请设置已保存：' + (j.on ? '开' : '关') + ' / ' + j.days + '天');
    } catch (e) {
      box(false, (e && e.message) || '保存失败');
    }
  }
  var _loadAdmin = window.loadAdmin;
  window.loadAdmin = async function () {
    if (typeof _loadAdmin === 'function') await _loadAdmin();
    ensure();
    load();
  };
  setTimeout(ensure, 800);
})();
