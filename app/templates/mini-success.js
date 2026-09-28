/* Paid success card + share. Does not touch pay endpoints. */
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
    if (!me || el('mycard-wrap')) return;
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
      '</div>' +
      '<p class="hint" id="mycard-hint">付费成功后可直接转发本卡</p>';
    var first = me.querySelector('.card');
    if (first && first.nextSibling) me.insertBefore(card, first.nextSibling);
    else me.insertBefore(card, me.firstChild);
    var share = el('btn-share-card');
    var copy = el('btn-copy-card');
    if (share) share.onclick = shareCard;
    if (copy) copy.onclick = copyCard;
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
      navigator.clipboard.writeText(text).then(
        function () {
          box(true, '已复制登记卡');
        },
        function () {
          box(false, '复制失败');
        }
      );
    } else box(true, text.slice(0, 80));
  }
  async function paint() {
    ensure();
    if (!window.user) return;
    var name = user.username || '';
    if (!name) {
      if (el('mycard')) el('mycard').textContent = '请先设置电报用户名后再出卡';
      return;
    }
    try {
      var q =
        '/api/mini/lookup?q=' +
        encodeURIComponent('@' + name) +
        '&user_id=' +
        user.id +
        '&init_data=' +
        encodeURIComponent(typeof initData !== 'undefined' ? initData : '');
      var j = await fetch(q).then(function (r) {
        return r.json();
      });
      if (el('mycard')) el('mycard').textContent = j.card || j.note || '暂无登记卡';
      if (el('mycard-hint')) {
        el('mycard-hint').textContent = j.found
          ? '可转发到群，以实时查询为准'
          : '开通并保存资料后出卡';
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
