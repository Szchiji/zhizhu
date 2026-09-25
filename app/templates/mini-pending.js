/* wave7: restore pending USDT checkout via GET /api/mini/pending */
(function () {
  function authQ() {
    return (
      'user_id=' +
      ((typeof user !== 'undefined' && user && user.id) || '') +
      '&init_data=' +
      encodeURIComponent(typeof initData !== 'undefined' ? initData : '')
    );
  }

  function ensureMeta() {
    var box = document.getElementById('checkout');
    if (!box) return null;
    var meta = document.getElementById('opending-meta');
    if (meta) return meta;
    meta = document.createElement('p');
    meta.id = 'opending-meta';
    meta.className = 'sub';
    var btns = box.querySelector('.btns');
    if (btns) box.insertBefore(meta, btns);
    else box.appendChild(meta);
    return meta;
  }

  function fillCheckout(p) {
    if (!p || !p.code) return false;
    var box = document.getElementById('checkout');
    if (!box) return false;
    box.classList.remove('hidden');
    var oid = document.getElementById('oid');
    var oamt = document.getElementById('oamt');
    var ochain = document.getElementById('ochain');
    var oaddr = document.getElementById('oaddr');
    if (oid) oid.textContent = p.code || '';
    if (oamt) oamt.textContent = (p.amount || '') + ' USDT';
    if (ochain) ochain.textContent = (p.chain || 'TRC20').toUpperCase();
    if (oaddr) oaddr.textContent = p.address || '';
    window._addr = p.address || '';
    var meta = ensureMeta();
    if (meta) {
      var st = p.status || 'pending';
      var stZh = { pending: '待支付', confirming: '链上确认中', draft: '草稿' }[st] || st;
      meta.textContent =
        '状态：' + stZh + (p.expires_at ? ' · 截止 ' + p.expires_at : '');
    }
    return true;
  }

  async function fetchPending() {
    if (typeof user === 'undefined' || !user) return null;
    var j = await fetch('/api/mini/pending?' + authQ()).then(function (r) {
      return r.json();
    });
    return (j && j.pending) || null;
  }

  window.restorePending = async function restorePending() {
    try {
      var p = await fetchPending();
      if (p && fillCheckout(p) && typeof watchPaid === 'function') watchPaid();
    } catch (e) {}
  };

  if (typeof watchPaid === 'function') {
    var _watchPaid = watchPaid;
    window.watchPaid = async function () {
      var codeEl = document.getElementById('oid');
      var code = ((codeEl && codeEl.textContent) || '').trim();
      for (var i = 0; i < 48; i++) {
        await new Promise(function (r) {
          setTimeout(r, 5000);
        });
        try {
          var p = await fetchPending();
          if (!p) {
            try {
              var j = await fetch(
                '/api/mini/orders?user_id=' +
                  user.id +
                  '&init_data=' +
                  encodeURIComponent(initData)
              ).then(function (r) {
                return r.json();
              });
              var hit = (j.orders || []).find(function (o) {
                return o.code === code && o.status === 'active';
              });
              document.getElementById('checkout').classList.add('hidden');
              if (hit) {
                show(ok, '续费已到账，时效已叠加');
                if (typeof loadMe === 'function') loadMe();
                if (typeof loadOrders === 'function') loadOrders();
                if (typeof tab === 'function') tab('me');
              } else {
                show(ok, '订单已结束（到账或取消）');
              }
            } catch (e2) {
              document.getElementById('checkout').classList.add('hidden');
            }
            return;
          }
          if (!code || p.code === code) fillCheckout(p);
        } catch (e) {}
      }
      return _watchPaid.apply(this, arguments);
    };
  }

  if (typeof tab === 'function') {
    var _tab = tab;
    window.tab = function (name) {
      _tab.apply(this, arguments);
      if (name === 'pay') window.restorePending();
    };
  }

  function boot() {
    window.restorePending();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else setTimeout(boot, 0);
})();
