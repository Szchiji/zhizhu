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
  function tgUser() {
    if (typeof user !== 'undefined' && user) return user;
    try {
      return (window.Telegram && Telegram.WebApp && Telegram.WebApp.initDataUnsafe && Telegram.WebApp.initDataUnsafe.user) || null;
    } catch (e) {
      return null;
    }
  }
  function data() {
    if (typeof initData !== 'undefined' && initData) return initData;
    try {
      return (window.Telegram && Telegram.WebApp && Telegram.WebApp.initData) || '';
    } catch (e) {
      return '';
    }
  }
  function escapeHtml(s) {
    return String(s || '')
      .replace(/&/g, '&')
      .replace(/</g, '<')
      .replace(/>/g, '>');
  }
  function toHtml(raw) {
    var t = String(raw || '');
    if (!t) return '';
    if (t.indexOf('<') === -1) return escapeHtml(t).replace(/\n/g, '<br>');
    t = t.replace(/<(?!\/?\s*(?:b|strong|i|em|u|s|code|pre|blockquote|br|a|span)\b)[^>]*>/gi, '');
    return t.replace(/\n/g, '<br>');
  }
  function toPlain(raw) {
    return String(raw || '')
      .replace(/<br\s*\/?>/gi, '\n')
      .replace(/<\/blockquote>/gi, '\n')
      .replace(/<\/p>/gi, '\n')
      .replace(/<[^>]+>/g, '')
      .replace(/&/g, '&')
      .replace(/</g, '<')
      .replace(/>/g, '>')
      .replace(/"/g, '"')
      .replace(/&#39;/g, "'")
      .replace(/\n{3,}/g, '\n\n')
      .trim();
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
        '<div class="idcard" id="mycard">加载中…</div>' +
        '<div class="btns">' +
        '<button type="button" id="btn-share-card">发到私聊</button>' +
        '<button type="button" class="ghost" id="btn-copy-card">复制卡面</button>' +
        '</div>' +
        '<p class="hint">机器人会把正式卡发到私聊，长按即可转发到群</p>';
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
  function rawCard() {
    return el('mycard') ? el('mycard').getAttribute('data-raw') || el('mycard').innerText || '' : '';
  }
  async function shareCard() {
    try {
      var r = await fetch('/api/mini/send-card', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ init_data: data() }),
      });
      var j = await r.json();
      if (!r.ok || j.error) throw new Error(j.error || '发送失败');
      box(true, '已发到机器人私聊，关闭小程序后可转发');
    } catch (e) {
      box(false, (e && e.message) || '发送失败');
    }
  }
  function copyCard() {
    var text = toPlain(rawCard());
    if (!text) return;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () {
        box(true, '已复制登记卡');
      });
    }
  }
  function setCard(raw, uname) {
    var node = el('mycard');
    if (!node) return;
    node.setAttribute('data-raw', raw || '');
    if (uname) node.setAttribute('data-user', String(uname).replace(/^@/, ''));
    node.innerHTML = toHtml(raw || '暂无登记卡');
  }
  async function paint() {
    ensure();
    var u = tgUser();
    var init = data();
    try {
      var me = await fetch(
        '/api/mini/me?init_data=' +
          encodeURIComponent(init) +
          '&username=' +
          encodeURIComponent((u && u.username) || '') +
          '&display_name=' +
          encodeURIComponent((u && ((u.first_name || '') + ' ' + (u.last_name || '')).trim()) || '')
      ).then(function (r) {
        return r.json();
      });
      var uname = (me && me.username) || (u && u.username) || '';
      if (uname) {
        var j = await fetch(
          '/api/mini/lookup?q=' +
            encodeURIComponent('@' + uname) +
            '&init_data=' +
            encodeURIComponent(init)
        ).then(function (r) {
          return r.json();
        });
        setCard(j.card || me.card_text || '', uname);
      } else {
        setCard((me && me.card_text) || '请先设置电报用户名', '');
      }
    } catch (e) {
      setCard('登记卡加载失败', '');
    }
    try {
      var r = await fetch('/api/mini/referral?init_data=' + encodeURIComponent(init)).then(function (x) {
        return x.json();
      });
      if (el('invite-link')) el('invite-link').textContent = r.link || '暂无邀请链接';
      if (el('invite-hint') && r.days) {
        el('invite-hint').textContent = r.on
          ? '好友从此链接进来并开通，你获得 ' + r.days + ' 天'
          : '邀请暂未开启';
      }
    } catch (e) {
      if (el('invite-link')) el('invite-link').textContent = '邀请链接加载失败';
    }
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
  setTimeout(paint, 400);
  setTimeout(paint, 1200);
})();
