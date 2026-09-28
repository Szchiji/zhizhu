/* Stars: prefer bot DM invoice, no Telegram popup APIs. */
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
  if (typeof pay !== 'function') return;
  var prev = pay;
  window.pay = async function (btn, rail) {
    if (rail !== 'stars') return prev.apply(this, arguments);
    if (!user) {
      banner(false, '请从机器人打开');
      return;
    }
    btn.disabled = true;
    try {
      var j = await api('/api/mini/order', {
        plan: _planId || 'year',
        rail: 'stars',
        coupon: ((document.getElementById('pay-coupon') || {}).value || '').trim(),
      });
      if (j.sent) {
        banner(true, '折后 ' + (j.amount || '') + ' 星，账单已发到机器人，请返回聊天付款');
        try {
          if (tg && tg.close) setTimeout(function () { tg.close(); }, 800);
        } catch (e) {}
        btn.disabled = false;
        return;
      }
      banner(false, '请改用 USDT，或回机器人查看是否收到账单');
    } catch (e) {
      banner(false, (e && e.message) || '下单失败');
    }
    btn.disabled = false;
  };
})();
