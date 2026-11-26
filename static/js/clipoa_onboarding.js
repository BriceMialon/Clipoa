// Assistant de premier lancement + ligne « À faire maintenant » de l'accueil (API : /api/onboarding).
// Écrans : Bienvenue → Outils → Claude → Voix pro (facultatif) → Première vidéo → Réseau → Fini. Passable, relançable depuis Connexions.
(function () {
  "use strict";
  var KEY_RE = /sk-ant-[A-Za-z0-9_\-]{20,}/;
  var ORDER = ["welcome", "tools", "claude", "voice", "video", "social", "end"];
  var data = null, screen = "welcome", bg = null, keyFlow = false, keyBusy = false, toolsTimer = null;

  var CSS = ".ob-bg{z-index:120}.ob-modal{max-width:440px;gap:12px}.ob-title{margin:0;font-size:22px;color:var(--ink)}" +
    ".ob-body p{margin:0 0 10px;color:var(--ink-2);font-size:15px;line-height:1.45}.ob-foot{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-top:6px}" +
    ".ob-dots{display:flex;gap:6px}.ob-dot{width:28px;height:4px;border-radius:4px;background:var(--border-hi)}.ob-dot.on{background:var(--accent)}" +
    ".ob-line{display:flex;align-items:center;gap:10px;padding:8px 0;border-top:1px solid var(--border);color:var(--ink);font-size:14px}.ob-line .btn,.ob-line .ob-muted{margin-left:auto}" +
    ".ob-check{width:22px;height:22px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;font-size:12px;background:var(--glass-soft);color:var(--muted)}" +
    ".ob-check.ok{background:var(--ok,#22c55e);color:#fff}.ob-muted{color:var(--muted);font-size:12px}" +
    ".ob-steps{margin:0 0 10px 18px;padding:0;color:var(--ink-2);font-size:14px;line-height:1.6}" +
    ".ob-input{width:100%;box-sizing:border-box;padding:11px 13px;border-radius:12px;border:1px solid var(--border-hi);background:var(--glass-soft);color:var(--ink);font-size:15px}" +
    ".ob-next{display:flex;align-items:center;gap:10px;padding:12px 16px;margin:12px 0;border-radius:16px;border:1px solid var(--border);background:var(--glass)}" +
    ".ob-next-txt{flex:1;color:var(--ink);font-weight:600;font-size:15px}.ob-next-dot{width:8px;height:8px;border-radius:50%;background:var(--accent);flex:none}";
  var st = document.createElement("style"); st.textContent = CSS; document.head.appendChild(st);

  function $(id) { return document.getElementById(id); }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function say(msg) { if (typeof window.toast === "function") window.toast(msg); }
  function step(id) { return ((data && data.steps) || []).filter(function (s) { return s.id === id; })[0] || { done: false, items: [] }; }

  function api(method, body) {
    return fetch("/api/onboarding", {
      method: method, cache: "no-store",
      headers: body ? { "Content-Type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined
    }).then(function (r) { return r.json(); }).then(function (d) { if (!d.error) { data = d; renderNext(); } return d; })
      .catch(function () { return { error: "ClipRoll ne répond pas." }; });
  }

  // ---------- Ligne « À faire maintenant » sur l'accueil ----------
  function renderNext() {
    var box = $("home-next-step");
    if (!box || !data || !data.next) return;
    var n = data.next;
    box.innerHTML = '<div class="ob-next"><span class="ob-next-dot"></span><span class="ob-next-txt">' + esc(n.text) +
      '</span><button type="button" class="btn btn-coral btn-sm" id="ob-next-btn">' + esc(n.button) + '</button></div>';
    $("ob-next-btn").onclick = function () { runAction(n.action); };
  }

  function runAction(action) {
    if (action && action.indexOf("guide:") === 0) return open(action.slice(6));
    if (action === "watch" && typeof window.openTheaterMode === "function") return window.openTheaterMode(0);
    if (action === "publish" && typeof window.showView === "function") {
      window.showView("auto");
      var sel = $("pub-video");
      if (sel && data.next.video) { sel.value = data.next.video; if (typeof window.syncPostizFields === "function") window.syncPostizFields(true); }
      return;
    }
    if (typeof window.showView === "function") window.showView("accueil");
    var inp = $("home-quick-input");
    if (inp) { inp.focus(); inp.scrollIntoView({ behavior: "smooth", block: "center" }); }
  }

  // ---------- Fenêtre du guide ----------
  function ensureModal() {
    if (bg) return;
    bg = document.createElement("div");
    bg.className = "modal-bg ob-bg";
    bg.id = "modal-onboarding";
    bg.innerHTML = '<div class="modal ob-modal" role="dialog" aria-modal="true" aria-labelledby="ob-title"></div>';
    document.body.appendChild(bg);
  }

  function open(at) {
    ensureModal();
    var go = function () {
      screen = ORDER.indexOf(at) >= 0 ? at : firstTodo();
      bg.classList.add("open");
      draw();
    };
    data ? go() : api("GET").then(go);
  }

  function close() {
    if (bg) bg.classList.remove("open");
    keyFlow = false;
    clearTimeout(toolsTimer);
  }

  function firstTodo() {
    if (!step("tools").done) return "tools";
    if (!step("claude").done) return "claude";
    if (!step("video").done) return "video";
    if (!step("social").done) return "social";
    return "end";
  }

  function next() { screen = ORDER[Math.min(ORDER.indexOf(screen) + 1, ORDER.length - 1)]; draw(); }

  function skipAll() { api("POST", { action: "skip" }); close(); say("Tu pourras relancer le guide dans Connexions."); }

  function dots() {
    var idx = ORDER.indexOf(screen), out = "";
    for (var i = 1; i <= 5; i++) out += '<span class="ob-dot' + (i <= idx ? " on" : "") + '"></span>';
    return '<div class="ob-dots">' + out + "</div>";
  }

  function frame(title, body, primary, secondary) {
    var m = bg.querySelector(".ob-modal");
    m.innerHTML = (screen !== "welcome" && screen !== "end" ? dots() : "") +
      '<h2 id="ob-title" class="ob-title">' + title + "</h2>" + '<div class="ob-body">' + body + "</div>" +
      '<div class="ob-foot"><button type="button" class="btn btn-ghost btn-sm" id="ob-sec">' + esc(secondary || "Passer le guide") + "</button>" +
      (primary ? '<button type="button" class="btn btn-coral" id="ob-pri">' + esc(primary) + "</button>" : "") + "</div>";
    $("ob-sec").onclick = screen === "welcome" || screen === "end" ? (screen === "end" ? finish : skipAll) : next;
    return m;
  }

  function okLine(label, ok, extra) {
    return '<div class="ob-line"><span class="ob-check ' + (ok ? "ok" : "") + '">' + (ok ? "✓" : "…") + "</span><span>" + esc(label) + "</span>" + (extra || "") + "</div>";
  }

  function draw() {
    clearTimeout(toolsTimer);
    if (screen === "welcome") {
      frame("Bienvenue sur ClipRoll", "<p>On prépare tout en 5 étapes. Ça prend 3 minutes.</p>", "Commencer", "Passer");
      $("ob-pri").onclick = function () { screen = firstTodo(); if (screen === "end") screen = "tools"; draw(); };
    } else if (screen === "tools") drawTools();
    else if (screen === "claude") drawClaude();
    else if (screen === "voice") drawVoice();
    else if (screen === "video") drawVideo();
    else if (screen === "social") drawSocial();
    else {
      frame("C'est prêt 🎉", "<p>L'accueil te dira toujours quoi faire ensuite.</p>", "Aller à l'accueil", "Fermer");
      $("ob-pri").onclick = finish;
    }
  }

  function finish() {
    api("POST", { action: "finish" }); close();
    if (typeof window.showView === "function") window.showView("accueil");
  }

  function drawTools() {
    var s = step("tools"), lines = "", installing = false;
    (s.items || []).forEach(function (t) {
      installing = installing || t.installing;
      var extra = t.can_install && !t.installing ? '<button type="button" class="btn btn-ghost btn-xs ob-install" data-tool="' + esc(t.id) + '">Installer</button>'
        : (t.installing ? '<span class="ob-muted">installation…</span>' : "");
      lines += okLine(t.label, t.ok, extra);
    });
    frame("Les outils", (s.done ? "<p>Tout est installé.</p>" : "<p>ClipRoll vérifie ce qu'il faut pour fabriquer tes vidéos.</p>") + lines,
      s.done ? "Suivant" : null, s.done ? null : "Continuer quand même");
    if (s.done) $("ob-pri").onclick = next;
    Array.prototype.forEach.call(bg.querySelectorAll(".ob-install"), function (b) {
      b.onclick = function () {
        b.disabled = true;
        fetch("/api/tools/blender/install", { method: "POST" }).then(function () { return api("GET"); }).then(drawTools);
      };
    });
    if (!s.done) toolsTimer = setTimeout(function () { api("GET").then(function () { if (screen === "tools" && bg.classList.contains("open")) drawTools(); }); }, installing ? 4000 : 8000);
  }

  function drawClaude() {
    if (step("claude").done) {
      frame("Claude", okLine("Ton compte Claude est connecté.", true), "Suivant", " ");
      $("ob-pri").onclick = next;
      $("ob-sec").style.visibility = "hidden";
      return;
    }
    frame("Connecte Claude",
      "<p>Claude écrit tes vidéos. Il faut un compte Anthropic avec un peu de crédit.</p>" +
      '<ol class="ob-steps"><li>Clique sur le bouton.</li><li>Crée une clé et copie-la.</li><li>Reviens ici : c\'est automatique.</li></ol>' +
      '<input type="password" class="ob-input" id="ob-key" placeholder="Ou colle ta clé ici (sk-ant-…)" autocomplete="off">',
      "Ouvrir la page Claude", "Plus tard");
    $("ob-pri").onclick = function () {
      window.open("https://console.anthropic.com/settings/keys", "_blank", "noopener");
      keyFlow = true;
    };
    var inp = $("ob-key");
    inp.oninput = function () { var m = inp.value.match(KEY_RE); if (m) saveKey(m[0]); };
  }

  function saveKey(key) {
    if (keyBusy) return;
    keyBusy = true; say("Test de la clé…");
    fetch("/api/claude/api-key", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ key: key }) })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        keyBusy = false;
        if (d.error) return say("❌ " + d.error);
        keyFlow = false; say("✓ Claude est connecté");
        return api("GET").then(function () { if (screen === "claude") next(); });
      })
      .catch(function () { keyBusy = false; say("❌ ClipRoll ne répond pas."); });
  }

  window.addEventListener("focus", function () {
    if (!keyFlow || keyBusy || !navigator.clipboard || !navigator.clipboard.readText) return;
    navigator.clipboard.readText().then(function (t) {
      var m = String(t || "").match(KEY_RE);
      if (m) { var inp = $("ob-key"); if (inp) inp.value = m[0]; saveKey(m[0]); }
    }).catch(function () { /* lecture refusée : l'utilisateur colle à la main */ });
  });

  function drawVoice() {
    var el = window.ClipoaEleven;
    if (step("voice").done || !el) {
      frame("La voix", okLine(step("voice").done ? "ElevenLabs est connecté." : "La voix gratuite est prête.", true), "Suivant", " ");
      $("ob-pri").onclick = next;
      $("ob-sec").style.visibility = "hidden";
      return;
    }
    frame("Une voix plus naturelle ?", "<p>La voix gratuite est déjà prête. ElevenLabs (payant) donne une voix plus humaine.</p>" + el.portalHtml(),
      "Ouvrir ElevenLabs", "Garder la voix gratuite");
    $("ob-pri").onclick = el.openPortal;
    el.bindPortal(function () { api("GET").then(function () { if (screen === "voice") next(); }); });
  }

  function drawVideo() {
    frame("Ta première vidéo", '<p>Écris ton idée en une phrase. ClipRoll fait le reste.</p>' +
      '<input type="text" class="ob-input" id="ob-idea" maxlength="200" placeholder="Ex : 3 faits fous sur les pieuvres">',
      "Fabriquer", "Plus tard");
    var inp = $("ob-idea");
    inp.focus();
    inp.onkeydown = function (e) { if (e.key === "Enter") $("ob-pri").click(); };
    $("ob-pri").onclick = function () {
      var idea = inp.value.trim();
      if (!idea) return say("Écris ton idée.");
      var home = $("home-quick-input");
      if (!home || typeof window.submitHomeQuickPrompt !== "function") return say("Écris ton idée sur l'accueil.");
      var tab = document.querySelector('#home-quick-tabs [data-qmode="create"]');
      if (tab && typeof window.setHomeQuickMode === "function") window.setHomeQuickMode("create", tab);
      home.value = idea;
      window.submitHomeQuickPrompt();
      api("POST", { action: "video_started" });
      next();
    };
  }

  function drawSocial() {
    var s = step("social"), lines = "", any = false;
    (s.items || []).forEach(function (n) {
      any = any || n.ready;
      var extra = n.connected ? "" : (n.ready
        ? '<button type="button" class="btn btn-ghost btn-xs ob-social" data-net="' + esc(n.id) + '">Connecter</button>'
        : '<span class="ob-muted">bientôt</span>');
      lines += okLine(n.label, n.connected, extra);
    });
    var intro = step("video").done ? "<p>Ta vidéo se prépare. En attendant, connecte un réseau pour la publier.</p>"
      : "<p>Connecte un réseau pour publier en un clic.</p>";
    frame("Publier", intro + lines, s.done ? "Suivant" : null, s.done ? null : (any ? "Plus tard" : "Continuer"));
    if (s.done) $("ob-pri").onclick = next;
    Array.prototype.forEach.call(bg.querySelectorAll(".ob-social"), function (b) {
      b.onclick = function () {
        if (typeof window.connectSocialOAuth === "function") window.connectSocialOAuth(b.dataset.net, "reglages", true);
      };
    });
  }

  // ---------- Démarrage ----------
  window.ClipoaOnboarding = {
    open: function (at) { api("POST", { action: "restart" }).then(function () { open(at || "welcome"); }); },
    show: function (at) { open(at); },
    refresh: function () { return api("GET"); }
  };

  function boot() {
    api("GET").then(function (d) {
      // au retour d'une connexion réseau, on reprend là où on en était
      if (d && d.auto_open) open(/oauth_|open=reglages/i.test(location.search) ? firstTodo() : "welcome");
    });
    document.addEventListener("visibilitychange", function () { if (!document.hidden) api("GET"); });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();
})();
