/* wave7: coupons admin/redeem + order revoke UI + percent coupons */
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

  function wrapPayHooks() {
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
      var _pay = pay;
      window.pay = function (btn, rail) {
        return _pay(btn, rail);
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
      '<div class="btns"><button type="button" id="coupon-redeem-btn">兑换</button></div>';
    var ledger = document.getElementById('olist');
    var ledgerCard = ledger ? ledger.closest('.card') : null;
    if (ledgerCard) host.insertBefore(card, ledgerCard);
    else host.appendChild(card);
    document.getElementById('coupon-redeem-btn').onclick = redeemCoupon;
  }

  async function redeemCoupon() {
    var code = (document.getElementById('coupon-code').value || '').trim();
    try {
      var j = await postJson('/api/mini/coupon/redeem', { code: code });
      show(ok, j.message || ('已兑换 ' + (j.days || '') + ' 天'));
      if (typeof loadMe === 'function') loadMe();
    } catch (e) {
      show(err, e.message);
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
      '<p class="hint">折扣填 1–90，例如 20 表示本单减 20%。折扣码要在开通页使用；赠送天数码在「我的」页兑换。</p>' +
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
      show(ok, '已保存 ' + (j.code || '') + (kind === 'percent' ? ' · 折扣码' : ' · 赠天码'));
      if (j.code) document.getElementById('cp-code').value = j.code;
      loadCoupons();
    } catch (e) {
      show(err, e.message);
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
      show(err, '请填写订单号');
      return;
    }
    var yes = true;
    if (typeof confirmAct === 'function') {
      yes = await confirmAct('撤销开通', '撤销 ' + code + ' 将回退会员天数（不调用 Stars 官方退款），确认？');
    } else {
      yes = window.confirm('撤销 ' + code + '？');
    }
    if (!yes) return;
    try {
      var j = await postJson('/api/mini/admin/revoke', { code: code });
      show(ok, '已撤销 ' + (j.code || code) + (j.paid_until ? ' · 到期 ' + j.paid_until : ''));
      if (typeof searchOrders === 'function') searchOrders();
    } catch (e) {
      show(err, e.message);
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
