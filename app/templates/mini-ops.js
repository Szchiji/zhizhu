/* wave7: coupons; DOM toasts only; Stars invoice slug normalize */
(function () {
  function qAuth() {
    return (
      'user_id=' +
      ((typeof user !== 'undefined' && user && user.id) || '') +
      '&init_data=' +
      encodeURIComponent(typeof initData !== 'undefined' ? initData : '')
    );
  }

  async function postJson(path, body) {
    if (typeof api === 'function') return api(path, body || {});
    body = Object.assign(
      {
        init_data: typeof initData !== 'undefined' ? initData : '',
        user_id: (typeof user !== 'undefined' && user && user.id) || 0,
      },
      body || {}
    );
    var r = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    var j = await r.json();
    if (!r.ok || j.error) throw new Error(j.error || '请求失败');
    return j;
  }

  function couponCode() {
    return ((document.getElementById('pay-coupon') || {}).value || '').trim();
  }

  function toast(kind, msg) {
    var text = String(msg || '');
    var okEl = document.getElementById('ok');
    var errEl = document.getElementById('err');
    var useOk = kind === ok || kind === true || kind === 'ok';
    if (okEl) okEl.style.display = useOk ? 'block' : 'none';
    if (errEl) errEl.style.display = useOk ? 'none' : 'block';
    var el = useOk ? okEl : errEl;
    if (el) el.textContent = text;
    var hint = document.getElementById('coupon-redeem-msg');
    if (hint) hint.textContent = text;
    var payHint = document.getElementById('pay-coupon-hint');
    if (payHint && !useOk) payHint.textContent = text;
  }

  function invoiceLink(raw) {
    if (raw && typeof raw === 'object') raw = raw.url || raw.invoice_url || raw.invoice || '';
    var u = String(raw || '').trim();
    var m = u.match(/(?:\$|invoice\/)([A-Za-z0-9\-_=]+)/);
    if (m) return 'https://t.me/$' + m[1];
    if (u.indexOf('http://') === 0) u = 'https://' + u.slice(7);
    if (u.charAt(0) === '$') u = 'https://t.me/' + u;
    if (u.indexOf('t.me/') === 0) u = 'https://' + u;
    return u.split('?')[0];
  }

  function wrapPayHooks() {
    if (typeof show === 'function' && !window.__couponShowWrap) {
      window.__couponShowWrap = true;
      window.show = function (el, msg) {
        toast(el, msg);
      };
    }
    if (typeof api === 'function' && !window.__couponApiWrap) {
      window.__couponApiWrap = true;
      var _api = api;
      window.api = function (path, body) {
        if (path === '/api/mini/order') {
          var code = couponCode();
          if (code) body = Object.assign({}, body || {}, { coupon: code });
        }
        return _api(path, body);
      };
    }
    if (typeof pay === 'function' && !window.__couponPayWrap) {
      window.__couponPayWrap = true;
      window.pay = async function (btn, rail) {
        if (!user) {
          toast(err, '请从机器人打开');
          return;
        }
        btn.disabled = true;
        try {
          var j = await api('/api/mini/order', { plan: _planId || 'year', rail: rail });
          if (rail === 'stars' || j.invoice) {
            var inv = invoiceLink(j.invoice || j.invoice_alt);
            if (!inv || inv.indexOf('https://t.me/$') !== 0) {
              throw new Error('账单链接无效，请改用 USDT：' + String(j.invoice || '').slice(0, 80));
            }
            if (!tg || !tg.openInvoice) throw new Error('当前客户端不能打开 Stars 账单');
            try {
              tg.openInvoice(inv, async function (st) {
                if (st === 'paid') {
                  toast(ok, '支付成功');
                  try {
                    await api('/api/mini/stars-paid', {
                      payload: j.payload || '',
                      username: user && user.username,
                      display_name:
                        user && (user.first_name || '') + (user.last_name ? ' ' + user.last_name : ''),
                    });
                  } catch (e) {}
                  if (typeof loadMe === 'function') loadMe();
                  if (typeof tab === 'function') tab('me');
                }
                btn.disabled = false;
              });
            } catch (ie) {
              throw new Error('无法打开 Stars，请改用 USDT');
            }
            return;
          }
          if (j.address) {
            var checkout = document.getElementById('checkout');
            if (checkout) {
              checkout.classList.remove('hidden');
              if (document.getElementById('oid')) document.getElementById('oid').textContent = j.code || '';
              if (document.getElementById('oamt')) document.getElementById('oamt').textContent = (j.amount || '') + ' USDT';
              if (document.getElementById('ochain')) document.getElementById('ochain').textContent = (j.chain || 'TRC20').toUpperCase();
              if (document.getElementById('oaddr')) document.getElementById('oaddr').textContent = j.address || '';
            }
            toast(ok, '折后金额 ' + (j.amount || '') + ' USDT');
          }
        } catch (e) {
          toast(err, e.message || String(e));
        }
        btn.disabled = false;
      };
    }
  }

  function ensurePayCoupon() {
    var payTab = document.getElementById('tab-pay');
    if (!payTab || document.getElementById('pay-coupon')) {
      wrapPayHooks();
      return;
    }
    var card = payTab.querySelector('.card');
    if (!card) return;
    var box = document.createElement('div');
    box.innerHTML =
      '<label>折扣码（可空）</label>' +
      '<input id="pay-coupon" placeholder="优惠 X% 的折扣码" />' +
      '<p class="hint" id="pay-coupon-hint">赠送天数码请到「我的」页兑换。折扣码在本页填好再点 Stars / USDT。</p>';
    var btns = card.querySelector('.btns');
    if (btns) card.insertBefore(box, btns);
    else card.appendChild(box);
    wrapPayHooks();
  }

  function ensureRedeemCard() {
    var host = document.getElementById('tab-me');
    if (!host || document.getElementById('coupon-redeem-card')) return;
    var card = document.createElement('div');
    card.className = 'card';
    card.id = 'coupon-redeem-card';
    card.innerHTML =
      '<div class="kicker">Coupon</div><h1>兑换码</h1>' +
      '<p class="sub">仅用于「赠送天数」码。折扣码请回开通页填写。</p>' +
      '<label>兑换码</label><input id="coupon-code" placeholder="如 CP-XXXXXX" />' +
      '<div class="btns"><button type="button" id="coupon-redeem-btn">兑换</button></div>' +
      '<p class="hint" id="coupon-redeem-msg"></p>';
    var ledger = document.getElementById('olist');
    var ledgerCard = ledger ? ledger.closest('.card') : null;
    if (ledgerCard) host.insertBefore(card, ledgerCard);
    else host.appendChild(card);
    document.getElementById('coupon-redeem-btn').onclick = redeemCoupon;
  }

  async function redeemCoupon() {
    var code = (document.getElementById('coupon-code').value || '').trim();
    if (!code) {
      toast(err, '请输入兑换码');
      return;
    }
    try {
      var j = await postJson('/api/mini/coupon/redeem', { code: code });
      toast(ok, j.message || ('已兑换 ' + (j.days || '') + ' 天'));
      if (typeof loadMe === 'function') loadMe();
    } catch (e) {
      toast(err, e.message || '兑换失败');
    }
  }

  function ensureCouponsAdmin() {
    var nav = document.getElementById('admnav');
    var host = document.getElementById('tab-adm');
    if (!nav || !host || document.getElementById('asec-coupons')) return;
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.setAttribute('data-sec', 'coupons');
    btn.textContent = '兑换码';
    btn.onclick = function () {
      if (typeof admSec === 'function') admSec('coupons');
      loadCoupons();
    };
    nav.appendChild(btn);
    var sec = document.createElement('div');
    sec.className = 'adm-sec';
    sec.id = 'asec-coupons';
    sec.innerHTML =
      '<div class="card"><h2 class="sec">兑换码</h2>' +
      '<label>码（可空，空则自动生成）</label><input id="cp-code" placeholder="CP-XXXX" />' +
      '<label>类型</label><select id="cp-kind">' +
      '<option value="days">赠送天数</option>' +
      '<option value="percent">折扣百分比（优惠 X%）</option>' +
      '</select>' +
      '<label id="cp-val-lab">赠送天数</label>' +
      '<input id="cp-days" type="number" value="7" />' +
      '<p class="hint">折扣填 1–90，例如 20 表示本单减 20%。</p>' +
      '<label>最大兑换次数（可空=不限）</label><input id="cp-max" type="number" placeholder="不限" />' +
      '<label>备注</label><input id="cp-note" placeholder="活动说明" />' +
      '<div class="btns"><button type="button" id="cp-save">保存兑换码</button>' +
      '<button type="button" class="ghost" id="cp-refresh">刷新列表</button></div>' +
      '<div class="olist" id="cp-list">打开本页自动加载</div></div>';
    var audit = document.getElementById('asec-audit');
    if (audit) host.insertBefore(sec, audit);
    else host.appendChild(sec);
    document.getElementById('cp-save').onclick = saveCoupon;
    document.getElementById('cp-refresh').onclick = loadCoupons;
    var kind = document.getElementById('cp-kind');
    kind.onchange = function () {
      document.getElementById('cp-val-lab').textContent =
        kind.value === 'percent' ? '优惠百分比 1-90' : '赠送天数';
    };
  }

  async function loadCoupons() {
    var el = document.getElementById('cp-list');
    if (!el) return;
    try {
      var j = await fetch('/api/mini/admin/coupons?' + qAuth()).then(function (r) {
        return r.json();
      });
      if (j.error) {
        el.textContent = j.error;
        return;
      }
      var rows = j.coupons || [];
      if (!rows.length) {
        el.textContent = '暂无兑换码';
        return;
      }
      el.innerHTML = rows
        .map(function (c) {
          var max = c.max_redemptions == null ? '∞' : c.max_redemptions;
          var kind = (c.kind || 'days') === 'percent' ? '折扣 ' + (c.value_days || 0) + '%' : (c.value_days || 0) + '天';
          return (
            '<div><b>' +
            (c.code || '') +
            '</b> · ' +
            kind +
            ' · 已兑 ' +
            (c.redeemed_count || 0) +
            '/' +
            max +
            (c.note ? ' · ' + c.note : '') +
            '</div>'
          );
        })
        .join('');
    } catch (e) {
      el.textContent = e.message || '加载失败';
    }
  }

  async function saveCoupon() {
    try {
      var kind = document.getElementById('cp-kind').value || 'days';
      var body = {
        code: (document.getElementById('cp-code').value || '').trim(),
        kind: kind,
        value_days: Number(document.getElementById('cp-days').value || (kind === 'percent' ? 10 : 7)),
        note: (document.getElementById('cp-note').value || '').trim(),
      };
      var max = (document.getElementById('cp-max').value || '').trim();
      if (max !== '') body.max_redemptions = Number(max);
      var j = await postJson('/api/mini/admin/coupons', body);
      toast(ok, '已保存 ' + (j.code || '') + (kind === 'percent' ? ' · 折扣码' : ' · 赠天码'));
      if (j.code) document.getElementById('cp-code').value = j.code;
      loadCoupons();
    } catch (e) {
      toast(err, e.message);
    }
  }

  function ensureRevokeBtn() {
    var sec = document.getElementById('asec-orders');
    if (!sec || document.getElementById('abtn-revoke')) return;
    var btns = sec.querySelector('.btns:last-of-type') || sec.querySelector('.btns');
    if (!btns) return;
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'ghost';
    b.id = 'abtn-revoke';
    b.textContent = '撤销开通';
    b.onclick = revokeOrder;
    btns.appendChild(b);
  }

  async function revokeOrder() {
    var code = ((document.getElementById('acode') || {}).value || '').trim();
    if (!code) {
      toast(err, '请填写订单号');
      return;
    }
    var yes = window.confirm('撤销 ' + code + '？');
    if (!yes) return;
    try {
      var j = await postJson('/api/mini/admin/revoke', { code: code });
      toast(ok, '已撤销 ' + (j.code || code));
      if (typeof searchOrders === 'function') searchOrders();
    } catch (e) {
      toast(err, e.message);
    }
  }

  if (typeof loadAdmin === 'function') {
    var _loadAdmin = loadAdmin;
    window.loadAdmin = async function () {
      await _loadAdmin.apply(this, arguments);
      ensureCouponsAdmin();
      ensureRevokeBtn();
    };
  }

  if (typeof tab === 'function') {
    var _tab = tab;
    window.tab = function (name) {
      _tab.apply(this, arguments);
      wrapPayHooks();
      if (name === 'pay') ensurePayCoupon();
      if (name === 'me') ensureRedeemCard();
      if (name === 'adm') {
        ensureCouponsAdmin();
        ensureRevokeBtn();
      }
    };
  }

  function boot() {
    try {
      if (window.Telegram && Telegram.WebApp && Telegram.WebApp.showAlert) {
        Telegram.WebApp.showAlert = function (msg) {
          toast(err, msg);
        };
      }
    } catch (e) {}
    ensurePayCoupon();
    ensureRedeemCard();
    ensureCouponsAdmin();
    ensureRevokeBtn();
    wrapPayHooks();
    setTimeout(wrapPayHooks, 400);
    setTimeout(wrapPayHooks, 1200);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else setTimeout(boot, 0);
})();
