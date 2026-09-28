/* Dedicated USDT + Stars handlers. No Telegram popups. */
(function () {
  function banner(okFlag, msg) {
    var text = String(msg || '');
    var el = document.getElementById(okFlag ? 'ok' : 'err');
    if (el) {
      el.style.display = 'block';
      el.textContent = text;
    }
    var hint = document.getElementById('pay-coupon-hint');
    if (hint) hint.textContent = text;
  }
  function coupon() {
    return ((document.getElementById('pay-coupon') || {}).value || '').trim();
  }
  function showUsdt(j) {
    var checkout = document.getElementById('checkout');
    if (checkout) checkout.classList.remove('hidden');
    if (document.getElementById('oid')) document.getElementById('oid').textContent = j.code || '';
    if (document.getElementById('oamt')) document.getElementById('oamt').textContent = (j.amount || '') + ' USDT';
    if (document.getElementById('ochain')) document.getElementById('ochain').textContent = (j.chain || 'TRC20').toUpperCase();
    if (document.getElementById('oaddr')) document.getElementById('oaddr').textContent = j.address || '';
    window._addr = j.address || '';
    banner(true, '请转账 ' + (j.amount || '') + ' USDT，订单 ' + (j.code || ''));
  }
  window.pay = async function (btn, rail) {
    if (!user) {
      banner(false, '请从机器人打开');
      return;
    }
    btn.disabled = true;
    try {
      if (rail === 'usdt') {
        var u = await api('/api/mini/pay-usdt', {
          plan: _planId || 'year',
          coupon: coupon(),
        });
        showUsdt(u);
        btn.disabled = false;
        return;
      }
      var j = await api('/api/mini/order', {
        plan: _planId || 'year',
        rail: 'stars',
        coupon: coupon(),
      });
      if (j.sent) {
        banner(true, '折后 ' + (j.amount || '') + ' 星，账单已发到机器人，请返回聊天付款');
        try {
          if (tg && tg.close) setTimeout(function () { tg.close(); }, 600);
        } catch (e) {}
        btn.disabled = false;
        return;
      }
      banner(false, '请改用 USDT 付款');
    } catch (e) {
      var msg = (e && e.message) || '下单失败';
      if (/expected pattern/i.test(msg)) msg = '请改用 USDT。Stars 账单被 Telegram 拒绝。';
      banner(false, msg);
    }
    btn.disabled = false;
  };
})();
