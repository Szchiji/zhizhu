/* Open Stars invoice with official slug shapes only. */
(function () {
  function slugFrom(url) {
    var u = String(url || '');
    if (u && typeof url === 'object') u = url.url || url.invoice_url || '';
    var m = String(u).match(/(?:\$|invoice\/)([A-Za-z0-9\-_=]+)/);
    return m ? m[1] : '';
  }
  function openStars(url, cb) {
    var slug = slugFrom(url);
    var list = [];
    if (slug) {
      list.push('https://t.me/$' + slug);
      list.push('https://t.me/invoice/' + slug);
    }
    var raw = String(url || '').trim();
    if (raw) list.push(raw.split('?')[0]);
    var last;
    for (var i = 0; i < list.length; i++) {
      try {
        tg.openInvoice(list[i], cb);
        return true;
      } catch (e) {
        last = e;
      }
    }
    if (tg.openTelegramLink && slug) {
      try {
        tg.openTelegramLink('https://t.me/$' + slug);
        return true;
      } catch (e2) {
        last = e2;
      }
    }
    throw last || new Error('无法打开 Stars 账单');
  }
  if (typeof pay === 'function') {
    var prev = pay;
    window.pay = async function (btn, rail) {
      if (rail !== 'stars') return prev.apply(this, arguments);
      if (!user) {
        if (tg && tg.showAlert) tg.showAlert('请从机器人打开');
        return;
      }
      btn.disabled = true;
      try {
        var j = await api('/api/mini/order', {
          plan: _planId || 'year',
          rail: 'stars',
          coupon: ((document.getElementById('pay-coupon') || {}).value || '').trim(),
        });
        var inv = j.invoice || j.invoice_alt || '';
        openStars(inv, async function (st) {
          if (st === 'paid') {
            try {
              await api('/api/mini/stars-paid', { payload: j.payload || '' });
            } catch (e) {}
            if (tg && tg.showAlert) tg.showAlert('支付成功');
            if (typeof loadMe === 'function') loadMe();
            if (typeof tab === 'function') tab('me');
          }
          btn.disabled = false;
        });
      } catch (e) {
        var msg = e && e.message ? e.message : String(e);
        if (/expected pattern|InvoiceUrlInvalid/i.test(msg)) msg = '账单链接打不开，请改用 USDT 或关掉小程序重试';
        if (tg && tg.showAlert) tg.showAlert(msg);
        else window.alert(msg);
        btn.disabled = false;
      }
    };
  }
})();
