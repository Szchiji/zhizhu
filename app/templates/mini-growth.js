/* Viral growth W1: ref bind, landing banner, query share, invite progress. */
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
    try {
      if (window.tg && tg.showPopup) {
        tg.showPopup({
          title: ok ? '已完成' : '提示',
          message: String(msg || ''),
          buttons: [{ id: 'ok', type: 'ok', text: '好的' }],
        });
        return;
      }
    } catch (e) {}
  }
  function data() {
    if (typeof initData !== 'undefined' && initData) return initData;
    try {
      return (window.Telegram && Telegram.WebApp && Telegram.WebApp.initData) || '';
    } catch (e) {
      return '';
    }
  }
  function tgObj() {
    try {
      return (window.Telegram && Telegram.WebApp) || null;
    } catch (e) {
      return null;
    }
  }
  function escapeHtml(s) {
    return String(s || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }
  function botName() {
    try {
      var u =
        (window.__botUsername ||
          (tgObj() && tgObj().initDataUnsafe && tgObj().initDataUnsafe.receiver && tgObj().initDataUnsafe.receiver.username) ||
          '') + '';
      return String(u).replace(/^@/, '');
    } catch (e) {
      return '';
    }
  }
  function parseStart() {
    var sp = '';
    var src = '';
    var ref = '';
    try {
      var tg = tgObj();
      if (tg && tg.initDataUnsafe && tg.initDataUnsafe.start_param) {
        sp = String(tg.initDataUnsafe.start_param || '');
      }
    } catch (e) {}
    try {
      var qs = new URLSearchParams(location.search || '');
      if (!sp) sp = qs.get('startapp') || qs.get('tgWebAppStartParam') || '';
      ref = qs.get('ref') || '';
      src = qs.get('src') || '';
    } catch (e) {}
    if (!sp && ref) {
      sp = 'ref_' + ref + '_src_' + (src || 'invite');
    }
    return { start_param: sp, ref: ref, src: src };
  }
  function ensureStyle() {
    if (el('growth-w1-style')) return;
    var s = document.createElement('style');
    s.id = 'growth-w1-style';
    s.textContent =
      '.gift-banner{background:linear-gradient(120deg,#5a4313,#2b210c 70%);border:1px solid rgba(212,175,55,.55);border-radius:16px;padding:16px;margin-bottom:12px;position:relative;overflow:hidden}' +
      '.gift-banner b{display:block;font-size:17px;color:#ffe3a1;padding-right:52px}' +
      '.gift-banner p{margin:4px 0 0;font-size:12px;color:#d9c391;line-height:1.55;padding-right:52px}' +
      '.gift-banner .meta{margin-top:8px;font-size:11px;color:#bfa66b}' +
      '.gift-banner:after{content:"🎁";position:absolute;right:12px;top:10px;font-size:36px;opacity:.9}' +
      '.inv-prog{height:12px;background:#0b0e14;border-radius:8px;border:1px solid var(--line);overflow:hidden;position:relative;margin-top:12px}' +
      '.inv-prog>i{position:absolute;left:0;top:0;bottom:0;background:linear-gradient(90deg,#d4af37,#f1d48a);border-radius:8px}' +
      '.inv-steps{display:flex;justify-content:space-between;font-size:11px;color:var(--muted);margin-top:6px}' +
      '.inv-steps b{color:var(--gold2)}' +
      '.inv-big{font-size:22px;font-weight:800;color:var(--gold2);margin-top:4px}' +
      '.inv-big small{font-size:13px;color:var(--muted);font-weight:500}' +
      '.inv-row{display:flex;align-items:center;gap:10px;padding:10px 0;border-bottom:1px solid var(--line);font-size:13px}' +
      '.inv-row:last-child{border:none}' +
      '.inv-av{width:34px;height:34px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:700;color:#fff;background:#4b7bd4;flex-shrink:0}' +
      '.inv-st{font-size:11px;padding:3px 8px;border-radius:20px;white-space:nowrap}' +
      '.inv-st.ok{background:rgba(76,195,138,.15);color:#4cc38a}' +
      '.inv-st.wait{background:rgba(139,147,161,.15);color:var(--muted)}' +
      '.q-actions{display:flex;gap:8px;margin-top:12px;flex-wrap:wrap}' +
      '.q-actions button{flex:1;min-width:120px}' +
      '.q-hint{font-size:11px;color:var(--muted);margin-top:10px;line-height:1.5}';
    document.head.appendChild(s);
  }
  window.__growth = window.__growth || { progress: null, banner: null, refCode: '' };

  async function bindRef() {
    var p = parseStart();
    if (!p.start_param && !p.ref) return null;
    try {
      var r = await fetch('/api/mini/ref/bind', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          init_data: data(),
          start_param: p.start_param,
          ref: p.ref,
          src: p.src,
        }),
      });
      var j = await r.json();
      if (j && j.banner) {
        window.__growth.banner = j.banner;
        paintBanner(j.banner);
      }
      return j;
    } catch (e) {
      return null;
    }
  }

  function paintBanner(b) {
    ensureStyle();
    if (!b || !b.show) {
      var old = el('gift-banner');
      if (old) old.remove();
      return;
    }
    var pay = el('tab-pay');
    if (!pay) return;
    var node = el('gift-banner');
    if (!node) {
      node = document.createElement('div');
      node.id = 'gift-banner';
      node.className = 'gift-banner';
      var first = pay.querySelector('.card');
      if (first) pay.insertBefore(node, first);
      else pay.insertBefore(node, pay.firstChild);
    }
    node.innerHTML =
      '<b>' +
      escapeHtml(b.title || '好友送你体验') +
      '</b><p>' +
      escapeHtml(b.subtitle || '') +
      '</p><div class="meta">ref=' +
      escapeHtml(b.ref_code || '') +
      ' · 已自动绑定，' +
      (b.bind_hours || 24) +
      ' 小时内有效</div>';
  }

  async function loadProgress() {
    try {
      var r = await fetch('/api/mini/invite/progress?init_data=' + encodeURIComponent(data())).then(function (x) {
        return x.json();
      });
      if (r && r.ok) {
        window.__growth.progress = r;
        window.__growth.refCode = r.ref_code || '';
        paintInvite(r);
        if (r.banner) {
          window.__growth.banner = r.banner;
          paintBanner(r.banner);
        }
      }
      return r;
    } catch (e) {
      return null;
    }
  }

  function paintInvite(p) {
    ensureStyle();
    var me = el('tab-me');
    if (!me || !p) return;
    var wrap = el('invite-wrap');
    if (!wrap) {
      wrap = document.createElement('div');
      wrap.className = 'card';
      wrap.id = 'invite-wrap';
      var my = el('mycard-wrap');
      if (my && my.nextSibling) me.insertBefore(wrap, my.nextSibling);
      else {
        var first = me.querySelector('.card');
        if (first && first.nextSibling) me.insertBefore(wrap, first.nextSibling);
        else me.appendChild(wrap);
      }
    }
    var shown = p.cycle_progress || 0;
    var target = p.cycle_target || 3;
    var need = p.need_more != null ? p.need_more : Math.max(0, target - shown);
    var days = p.reward_days || p.days || 7;
    var pct = target ? Math.min(100, (shown / target) * 100) : 0;
    var steps = [];
    for (var i = 0; i <= target; i++) {
      if (i === target) steps.push('<span>' + i + ' · 🎁 +' + days + ' 天</span>');
      else if (i === shown) steps.push('<span><b>' + i + '</b></span>');
      else steps.push('<span>' + i + '</span>');
    }
    var recentHtml = '';
    (p.recent || []).forEach(function (it) {
      var name = escapeHtml(it.name || '');
      var ch = (it.name || '?').toString().replace(/^@/, '').slice(0, 1);
      var ok = it.status === 'paid';
      recentHtml +=
        '<div class="inv-row"><div class="inv-av">' +
        escapeHtml(ch) +
        '</div><div style="flex:1"><b>' +
        name +
        '</b><div class="sub" style="font-size:11px">' +
        escapeHtml(it.src_label || '') +
        (it.ts ? ' · ' + escapeHtml(String(it.ts).replace('T', ' ').slice(0, 16)) : '') +
        '</div></div><span class="inv-st ' +
        (ok ? 'ok' : 'wait') +
        '">' +
        escapeHtml(it.status_label || it.status || '') +
        '</span></div>';
    });
    wrap.innerHTML =
      '<div class="kicker">Invite</div>' +
      '<h1>邀请好友得天数</h1>' +
      '<div class="inv-big" id="inv-title">已邀 ' +
      shown +
      ' <small>/ 再邀 ' +
      need +
      ' 人得 +' +
      days +
      ' 天</small></div>' +
      '<div class="inv-prog"><i style="width:' +
      pct +
      '%"></i></div>' +
      '<div class="inv-steps">' +
      steps.join('') +
      '</div>' +
      '<p class="sub" style="margin-top:10px">好友通过你的链接<b style="color:var(--text)">完成开通</b>才计入；每满 ' +
      target +
      ' 人奖励 ' +
      days +
      ' 天，自动叠加到有效期。</p>' +
      '<div class="mono" id="invite-link">' +
      escapeHtml(p.invite_link || p.link || '') +
      '</div>' +
      '<div class="btns">' +
      '<button type="button" class="ghost" id="btn-copy-invite">🔗 复制邀请链接</button>' +
      '<button type="button" id="btn-share-invite">↗ 分享邀请</button>' +
      '</div>' +
      (recentHtml
        ? '<div class="divider"></div><h2 class="sec" style="display:flex">最近邀请<span class="sub" style="margin-left:auto;font-weight:400">累计奖励 ' +
          (p.total_reward_days || 0) +
          ' 天</span></h2>' +
          recentHtml
        : '');
    var copyBtn = el('btn-copy-invite');
    if (copyBtn) {
      copyBtn.onclick = function () {
        copyText(p.invite_link || p.link || '', '邀请链接已复制');
      };
    }
    var shareBtn = el('btn-share-invite');
    if (shareBtn) {
      shareBtn.onclick = function () {
        shareInvite(p);
      };
    }
  }

  function copyText(text, msg) {
    if (!text) return;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () {
        box(true, msg || '已复制');
      });
      return;
    }
    box(true, msg || '已复制');
  }

  function shareUrl(url, text) {
    var tg = tgObj();
    var q = (text || '') + (url ? '\n' + url : '');
    try {
      if (tg && typeof tg.switchInlineQuery === 'function') {
        tg.switchInlineQuery(url || text || '', ['users', 'groups', 'supergroups']);
        return true;
      }
    } catch (e) {}
    try {
      if (tg && typeof tg.openTelegramLink === 'function' && url) {
        var share =
          'https://t.me/share/url?url=' + encodeURIComponent(url) + '&text=' + encodeURIComponent(text || '');
        tg.openTelegramLink(share);
        return true;
      }
    } catch (e) {}
    copyText(url || q, '链接已复制，可粘贴分享');
    return false;
  }

  function shareInvite(p) {
    var link = (p && (p.invite_link || p.link)) || '';
    var days = (p && (p.reward_days || p.days)) || 7;
    var text = '🎁 好友送你 ' + days + ' 天体验\n我在用身份核验防骗子仿冒。通过我的链接开通，额外送 ' + days + ' 天';
    shareUrl(link, text);
  }

  function deepLink(src) {
    var code = window.__growth.refCode || '';
    var bot = botName();
    if (!code) {
      var p = window.__growth.progress;
      if (p && p.ref_code) code = p.ref_code;
    }
    if (!bot || !code) return '';
    return 'https://t.me/' + bot + '/app?startapp=ref_' + code + '_src_' + (src || 'invite');
  }

  function enhanceLookup() {
    var prev = window.lookup;
    if (typeof prev !== 'function' || prev.__growthWrapped) return;
    window.lookup = async function () {
      await prev.apply(this, arguments);
      afterLookup();
    };
    window.lookup.__growthWrapped = true;
  }

  function afterLookup() {
    ensureStyle();
    var qtext = el('qtext');
    var qcard = el('qcard');
    if (!qtext || !qcard || qcard.classList.contains('hidden')) return;
    if (el('q-growth-actions')) el('q-growth-actions').remove();
    var cardBody = (qtext.querySelector('.idcard') || qtext).textContent || '';
    var found = !/暂无平台登记|尚未|未登记/.test(cardBody) && !!cardBody.trim();
    // Prefer structured flag if last lookup stored it
    if (typeof window.__lastLookupFound === 'boolean') found = window.__lastLookupFound;
    var boxEl = document.createElement('div');
    boxEl.id = 'q-growth-actions';
    var src = found ? 'found' : 'empty';
    var link = deepLink(src);
    if (found) {
      boxEl.innerHTML =
        '<div class="q-actions">' +
        '<button type="button" id="btn-share-result">↗ 分享到聊天</button>' +
        '<button type="button" class="ghost" id="btn-requery">↻ 再查一次</button>' +
        '</div>' +
        '<p class="q-hint">ⓘ 分享卡片自动带品牌水印与查询时间，并附带你的邀请参数，好友开通后你获得奖励天数。</p>';
    } else {
      boxEl.innerHTML =
        '<div class="q-actions">' +
        '<button type="button" id="btn-go-open">去开通 · 首登记送 ' +
        ((window.__growth.progress && (window.__growth.progress.reward_days || window.__growth.progress.days)) || 7) +
        ' 天</button>' +
        '</div>' +
        '<div class="q-actions">' +
        '<button type="button" class="ghost" id="btn-share-empty">↗ 分享空态卡（邀请对方登记）</button>' +
        '</div>' +
        (link ? '<div class="mono" style="margin-top:10px;font-size:11px">' + escapeHtml(link) + '</div>' : '') +
        '<p class="q-hint">ⓘ 空态卡深链携带你的 ref，对方开通后计入邀请进度。</p>';
    }
    qcard.appendChild(boxEl);
    if (el('btn-share-result')) {
      el('btn-share-result').onclick = function () {
        shareResult(true);
      };
    }
    if (el('btn-share-empty')) {
      el('btn-share-empty').onclick = function () {
        shareResult(false);
      };
    }
    if (el('btn-requery')) {
      el('btn-requery').onclick = function () {
        if (el('q')) {
          el('q').value = '';
          el('q').focus();
        }
        qcard.classList.add('hidden');
        box(true, '已清空，请重新输入');
      };
    }
    if (el('btn-go-open')) {
      el('btn-go-open').onclick = function () {
        if (typeof tab === 'function') tab('pay');
      };
    }
  }

  function shareResult(found) {
    var src = found ? 'found' : 'empty';
    var link = deepLink(src);
    var q = (el('q') && el('q').value) || '';
    var text = found
      ? '🛡️ 平台身份核验\n此账号完成登记\n查询：' + q + '\n打开核验 / 去登记'
      : '🛡️ 平台身份查询\n' + q + ' 尚未登记\n👉 本人可点链接登记，好友送你体验';
    if (!link) {
      // ensure progress loaded for code
      loadProgress().then(function () {
        link = deepLink(src);
        shareUrl(link, text);
      });
      return;
    }
    shareUrl(link, text);
  }

  // Wrap lookup fetch to capture found flag
  function wrapLookupFetch() {
    var prev = window.lookup;
    if (typeof prev !== 'function') return;
    window.lookup = async function () {
      var q = (el('q') && el('q').value.trim()) || '';
      try {
        var j = await fetch(
          '/api/mini/lookup?q=' +
            encodeURIComponent(q) +
            '&user_id=' +
            ((typeof user !== 'undefined' && user && user.id) || '') +
            '&init_data=' +
            encodeURIComponent(data())
        ).then(function (r) {
          return r.json();
        });
        window.__lastLookupFound = !!j.found;
        var boxCard = el('qcard');
        if (j.error) {
          box(false, j.error);
          return;
        }
        if (boxCard) boxCard.classList.remove('hidden');
        var html = '';
        if (j.matches && j.matches.length) {
          html +=
            '<div class="olist">' +
            j.matches
              .map(function (u) {
                return (
                  '<div class="pick" data-q="@' +
                  u.username +
                  '">@' +
                  u.username +
                  ' · ' +
                  (u.display_name || '') +
                  '</div>'
                );
              })
              .join('') +
            '</div>';
        }
        var body = j.found ? j.card || '' : j.card || '@' + (j.query || q) + ' 暂无平台登记';
        html += '<div class="idcard"></div>';
        el('qtext').innerHTML = html;
        var idc = el('qtext').querySelector('.idcard');
        if (idc) {
          // Prefer HTML if card looks like markup
          if (String(body).indexOf('<') >= 0) idc.innerHTML = body;
          else idc.textContent = body;
        }
        el('qtext').querySelectorAll('.pick').forEach(function (node) {
          node.onclick = function () {
            el('q').value = node.getAttribute('data-q');
            window.lookup();
          };
        });
        afterLookup();
      } catch (e) {
        box(false, (e && e.message) || '查询失败');
      }
    };
    window.lookup.__growthWrapped = true;
  }

  // Enrich referral GET with banner for pay tab
  async function bootBanner() {
    try {
      var r = await fetch('/api/mini/referral?init_data=' + encodeURIComponent(data())).then(function (x) {
        return x.json();
      });
      if (r && r.ref_code) window.__growth.refCode = r.ref_code;
      if (r && r.ok) window.__growth.progress = r;
      if (r && r.banner) {
        window.__growth.banner = r.banner;
        paintBanner(r.banner);
      }
    } catch (e) {}
  }

  var _loadMe = window.loadMe;
  window.loadMe = async function () {
    if (typeof _loadMe === 'function') await _loadMe();
    await loadProgress();
  };

  var _tab = window.tab;
  if (typeof _tab === 'function') {
    window.tab = function (name) {
      _tab(name);
      if (name === 'me') loadProgress();
      if (name === 'pay') {
        if (window.__growth.banner) paintBanner(window.__growth.banner);
        else bootBanner();
      }
    };
  }

  ensureStyle();
  wrapLookupFetch();
  setTimeout(function () {
    bindRef().then(function () {
      bootBanner();
      loadProgress();
    });
  }, 300);
  setTimeout(loadProgress, 1400);
})();
