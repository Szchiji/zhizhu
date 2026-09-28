/* Coupon redeem without Telegram popup APIs. */
(function () {
  function banner(okFlag, msg) {
    var text = String(msg || '');
    var el = document.getElementById(okFlag ? 'ok' : 'err');
    if (el) {
      el.style.display = 'block';
      el.textContent = text;
    }
    var hint = document.getElementById('coupon-redeem-msg');
    if (hint) hint.textContent = text;
  }

  async function redeemSafe() {
    var input = document.getElementById('coupon-code');
    var code = ((input && input.value) || '').trim();
    if (!code) {
      banner(false, '请输入兑换码');
      return;
    }
    try {
      var r = await fetch('/api/mini/coupon/redeem', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          code: code,
          init_data: typeof initData !== 'undefined' ? initData : '',
          user_id: (typeof user !== 'undefined' && user && user.id) || 0,
        }),
      });
      var j = {};
      try {
        j = await r.json();
      } catch (e) {
        banner(false, '兑换接口无法解读');
        return;
      }
      if (!r.ok || j.error) {
        banner(false, j.error || '兑换失败');
        return;
      }
      banner(true, j.message || ('已兑换 ' + (j.days || '') + ' 天'));
      if (typeof loadMe === 'function') loadMe();
    } catch (e) {
      banner(false, (e && e.message) || '兑换失败');
    }
  }

  function hook() {
    var btn = document.getElementById('coupon-redeem-btn');
    if (!btn) return;
    btn.onclick = function (ev) {
      if (ev) ev.preventDefault();
      redeemSafe();
    };
    var card = document.getElementById('coupon-redeem-card');
    if (card && !document.getElementById('coupon-redeem-msg')) {
      var p = document.createElement('p');
      p.className = 'hint';
      p.id = 'coupon-redeem-msg';
      card.appendChild(p);
    }
  }
  hook();
  setTimeout(hook, 400);
  setTimeout(hook, 1200);
})();
