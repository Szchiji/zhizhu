  function remountCardBars() {
    var sec = document.getElementById("asec-card");
    if (sec) sec.querySelectorAll(".phbar,.emobar").forEach(function (el) { el.remove(); });
    document.querySelectorAll('.tgbar[data-ph="card"]').forEach(function (bar) {
      bar.innerHTML = "";
      delete bar.dataset.ready;
      var id = bar.getAttribute("data-for");
      var tools = typeof TG_TOOLS !== "undefined" ? TG_TOOLS : [];
      tools.forEach(function (tool) {
        var b = document.createElement("button");
        b.type = "button";
        b.textContent = tool.label;
        b.title = tool.title || tool.label;
        b.addEventListener("click", function () { applyTool(id, tool); });
        bar.appendChild(b);
      });
      var phList = typeof TG_PH_CARD !== "undefined" ? TG_PH_CARD : [];
      var phbar = document.createElement("div");
      phbar.className = "phbar";
      phList.forEach(function (ph) {
        var b = document.createElement("button");
        b.type = "button";
        b.textContent = ph.label;
        b.title = "插入占位符 " + ph.value;
        b.addEventListener("click", function () { insertInto(id, "ph", ph.value); });
        phbar.appendChild(b);
      });
      bar.parentNode.insertBefore(phbar, bar.nextSibling);
      var emobar = document.createElement("div");
      emobar.className = "emobar";
      var lab = document.createElement("div");
      lab.className = "emobar-label";
      lab.textContent = LABELS[id] || "自定义表情";
      emobar.appendChild(lab);
      var sel = document.createElement("select");
      var opt0 = document.createElement("option");
      opt0.value = "";
      opt0.textContent = "自定义表情…";
      sel.appendChild(opt0);
      var emos = typeof TG_CUSTOM_EMOJI !== "undefined" ? TG_CUSTOM_EMOJI : [];
      emos.forEach(function (em, i) {
        var o = document.createElement("option");
        o.value = String(i);
        o.textContent = em.fallback + " " + em.name;
        sel.appendChild(o);
      });
      var btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = "插入表情";
      var doIns = function () {
        if (sel.value === "") {
          if (typeof show === "function") show(err, "请先选择一个自定义表情");
          return;
        }
        insertInto(id, "emoji", emos[Number(sel.value)]);
      };
      btn.addEventListener("click", doIns);
      sel.addEventListener("change", function () { if (sel.value !== "") doIns(); });
      var paste = document.createElement("button");
      paste.type = "button";
      paste.textContent = "粘贴ID";
      paste.addEventListener("click", function () { insertInto(id, "emoji-prompt"); });
      emobar.appendChild(sel);
      emobar.appendChild(btn);
      emobar.appendChild(paste);
      phbar.parentNode.insertBefore(emobar, phbar.nextSibling);
      bar.dataset.ready = "1";
    });
  }

  function wrapApi(name, before, after) {
    var orig = window[name];
    if (typeof orig !== "function") return;
    window[name] = async function () {
      if (before) before();
      var r = await orig.apply(this, arguments);
      if (after) after();
      return r;
    };
  }
  function wrapApis() {
    wrapApi("loadCardTpl", null, paintAll);
    wrapApi("saveCardTpl", syncAll, paintAll);
    wrapApi("cardPack", null, paintAll);
    var prev = window.previewTpl;
    if (typeof prev === "function") {
      window.previewTpl = function (id) {
        if (IDS.indexOf(id) >= 0) syncOne(id);
        return prev.apply(this, arguments);
      };
    }
  }

  function boot() {
    ensureSurfaces();
    remountCardBars();
    wrapApis();
    paintAll();
    setTimeout(paintAll, 600);
    setTimeout(paintAll, 1800);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
