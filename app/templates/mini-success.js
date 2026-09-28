/* Paid success card + invite link. */
(function () {
  function el(id) {
    return document.getElementById(id);
  }
  function box(ok, msg) {
    var a = el(ok ? 'ok' : 'err');
    if (a) {
      a.style.display = 'block';
      a.textContent = String(msg || '');
    }
  }
  function ensure() {
    var me = el('tab-me');
    if (!me) return;
    if (!el('mycard-wrap')) {
      var card = document.createElement('div');
      card.className = 'card';
      card.id = 'mycard-wrap';
      card.innerHTML =
        '<div class="kicker">Official Card</div>' +
        '<h1>我的登记卡</h1>' +
        '<div class="idcard" id="mycard">开通后在此显示</div>' +
        '<div class="btns">' +
        '<button type="button" id="btn-share-card">转发到群</button>' +
        '<button type="button" class="ghost" id="btn-copy-card">复制卡面</button>' +
        '</div>';
      var first = me.querySelector('.card');
      if (first && first.nextSibling) me.insertBefore(card, first.nextSibling);
      else me.insertBefore(card, me.firstChild);
      if (el('btn-share-card')) el('btn-share-card').onclick = shareCard;
      if (el('btn-copy-card')) el('btn-copy-card').onclick = copyCard;
    }
    if (!el('invite-wrap')) {
      var inv = document.createElement('div');
      inv.className = 'card';
      inv.id = 'invite-wrap';
      inv.innerHTML =
        '<div class="kicker">Invite</div>' +
        '<h1>邀请好友</h1>' +
        '<p class="sub" id="invite-hint">好友开通后，你获得奖励天数</p>' +
        '<div class="mono" id="invite-link">加载中…</div>' +
        '<div class="btns"><button type="button" id="btn-copy-invite">复制邀请链接</button></div>';
      var wrap = el('mycard-wrap');
      if (wrap && wrap.nextSibling) me.insertBefore(inv, wrap.nextSibling);
      else me.appendChild(inv);
      if (el('btn-copy-invite')) {
        el('btn-copy-invite').onclick = function () {
          var t = (el('invite-link') || {}).textContent || '';
          if (!t || t.indexOf('http') !== 0) return;
          if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(t).then(function () {
              box(true, '已复制邀请链接');
            });
          }
        };
      }
    }
  }
  function cardText() {
    return ((el('mycard') || {}).textContent || '').trim();
  }
  function shareCard() {
    var text = cardText();
    if (!text || text === '开通后在此显示') {
      box(false, '还没有可转发的卡');
      return;
    }
    var url =
      'https://t.me/share/url?url=' +
      encodeURIComponent('https://t.me/' + ((window._botName || '') + '').replace(/^@/, '')) +
      '&text=' +
      encodeURIComponent(text.slice(0, 900));
    if (window.tg && tg.openTelegramLink) tg.openTelegramLink(url);
    else window.open(url, '_blank');
  }
  function copyCard() {
    var text = cardText();
    if (!text) return;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () {
        box(true, '已复制登记卡');
      });
    }
  }
  async function paint() {
    ensure();
    if (!window.user) return;
    var name = user.username || '';
    if (name && el('mycard')) {
      try {
        var q =
          '/api/mini/lookup?q=' +
          encodeURIComponent('@' + name) +
          '&init_data=' +
          encodeURIComponent(typeof initData !== 'undefined' ? initData : '');
        var j = await fetch(q).then(function (r) {
          return r.json();
        });
        el('mycard').textContent = j.card || j.note || '暂无登记卡';
      } catch (e) {}
    }
    try {
      var r = await fetch(
        '/api/mini/referral?init_data=' + encodeURIComponent(typeof initData !== 'undefined' ? initData : '')
      ).then(function (x) {
        return x.json();
      });
      if (el('invite-link')) el('invite-link').textContent = r.link || '暂无邀请链接';
      if (el('invite-hint') && r.days) {
        el('invite-hint').textContent = r.on
          ? '好友从此链接进来并开通，你获得 ' + r.days + ' 天'
          : '邀请暂未开启';
      }
    } catch (e) {}
  }
  var _loadMe = window.loadMe;
  window.loadMe = async function () {
    if (typeof _loadMe === 'function') await _loadMe();
    await paint();
  };
  var _goMe = window.goMe;
  window.goMe = function (msg) {
    if (typeof _goMe === 'function') _goMe(msg);
    else if (typeof tab === 'function') tab('me');
    paint();
  };
  ensure();
  setTimeout(paint, 600);
})();
