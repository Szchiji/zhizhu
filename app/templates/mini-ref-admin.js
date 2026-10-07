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
      '<p class="hint">好友从邀请链接进来并完成开通才计入；每满 N 人给邀请人叠加天数，被邀请人额外获得同等天数。</p>' +
      '<label>每轮奖励天数</label>' +
      '<input id="ref-days" type="number" min="1" max="365" value="7" />' +
      '<label>每轮邀请人数</label>' +
      '<input id="ref-cycle" type="number" min="1" max="50" value="3" />' +
      '<label>归因绑定有效小时</label>' +
      '<input id="ref-bind-hours" type="number" min="1" max="720" value="24" />' +
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
      if (document.getElementById('ref-days')) document.getElementById('ref-days').value = r.days || r.reward_days || 7;
      if (document.getElementById('ref-cycle')) document.getElementById('ref-cycle').value = r.cycle_target || 3;
      if (document.getElementById('ref-bind-hours')) {
        document.getElementById('ref-bind-hours').value = r.bind_hours || 24;
      }
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
          cycle: (document.getElementById('ref-cycle') || {}).value || 3,
          bind_hours: (document.getElementById('ref-bind-hours') || {}).value || 24,
        }),
      });
      var j = await r.json();
      if (!r.ok || j.error) throw new Error(j.error || '保存失败');
      window._refOn = !!j.on;
      box(
        true,
        '邀请设置已保存：' +
          (j.on ? '开' : '关') +
          ' / 每 ' +
          (j.cycle || 3) +
          ' 人 +' +
          j.days +
          ' 天 / 绑定 ' +
          (j.bind_hours || 24) +
          'h'
      );
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
