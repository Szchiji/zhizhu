/* Coupon redeem + dual-rail price preview. */
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
        }),
      });
      var raw = await r.text();
      var j = {};
      try {
        j = JSON.parse(raw);
      } catch (e) {
        banner(false, raw ? raw.slice(0, 80) : '兑换失败');
        return;
      }
      if (!r.ok || j.error) {
        banner(false, j.error || j.detail || '兑换失败');
        return;
      }
      banner(true, j.message || ('已兑换 ' + (j.days || '') + ' 天'));
      if (typeof loadMe === 'function') loadMe();
      if (typeof tab === 'function') tab('me');
    } catch (e) {
      banner(false, (e && e.message) || '兑换失败');
    }
  }

  async function paintPrice() {
    var list = typeof _plans !== 'undefined' ? _plans : [];
    var p = null;
    for (var i = 0; i < list.length; i++) {
      if (list[i].id === (_planId || 'year')) p = list[i];
    }
    if (!p) p = list[0];
    if (!p) return;
    var off = 0;
    var code = ((document.getElementById('pay-coupon') || {}).value || '').trim();
    if (code) {
      try {
        var q =
          'code=' +
          encodeURIComponent(code) +
          '&init_data=' +
          encodeURIComponent(typeof initData !== 'undefined' ? initData : '');
        var prev = await fetch('/api/mini/coupon/preview?' + q).then(function (r) {
          return r.json();
        });
        if (prev && prev.percent_off) off = Number(prev.percent_off) || 0;
      } catch (e) {}
    }
    var stars = Number(p.stars || 0);
    var usdt = Number(p.usdt || 0);
    var sNow = off ? Math.max(1, Math.round((stars * (100 - off)) / 100)) : stars;
    var uNow = off ? Math.max(0.01, Math.round(usdt * (100 - off)) / 100) : usdt;
    var el = document.getElementById('planprice');
    if (el) {
      el.innerHTML = off
        ? '<s>' + stars + '</s> ' + sNow + ' ⭐ · <s>' + usdt + '</s> ' + uNow + ' USDT · ' + (p.label || '') + ' · 优惠 ' + off + '%'
        : stars + ' ⭐ · ' + usdt + ' USDT · ' + (p.label || '');
    }
    var hint = document.getElementById('pay-coupon-hint');
    if (hint && off) hint.textContent = '折后 ' + sNow + ' 星 / ' + uNow + ' USDT';
  }

  function hook() {
    var btn = document.getElementById('coupon-redeem-btn');
    if (btn) {
      btn.onclick = function (ev) {
        if (ev) ev.preventDefault();
        redeemSafe();
      };
    }
    var inp = document.getElementById('pay-coupon');
    if (inp && !inp.__priceHook) {
      inp.__priceHook = true;
      inp.addEventListener('input', paintPrice);
      inp.addEventListener('change', paintPrice);
    }
  }
  hook();
  paintPrice();
  setTimeout(hook, 400);
  setTimeout(paintPrice, 500);
  setTimeout(hook, 1200);
})();
