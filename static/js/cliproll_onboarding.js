// Assistant de premier lancement + visite interactive de la barre latérale + ligne « À faire maintenant » (API : /api/onboarding).
// Écrans : Bienvenue → Visite du studio (barre latérale) → Outils → Claude → Voix pro (facultatif) → Première vidéo → Réseau → Fini.
(function () {
  "use strict";
  var KEY_RE = /sk-ant-[A-Za-z0-9_\-]{20,}/;
  var ORDER = ["welcome", "tour", "profile", "tools", "claude", "voice", "video", "social", "end"];
  var TOUR_STOPS = [
    {
      view: "accueil",
      badge: "1 / 8",
      title: "Accueil — Ton QG rapide",
      desc: "Écris une idée en une phrase pour lancer une vidéo aussitôt, retrouve tes shorts à valider qui défilent en un coup d'œil et suis ton planning de la semaine.",
      tip: "Astuce : commence toujours ici quand tu veux créer vite."
    },
    {
      view: "creer",
      badge: "2 / 8",
      title: "Créer — Le studio complet",
      desc: "Écris ton sujet ou colle ton propre script, fais-le écrire ou améliorer par l'IA, puis choisis le style visuel, la voix, la musique et les bruitages.",
      tip: "Astuce : tu peux aussi tester l'optimiseur de rétention avant de fabriquer."
    },
    {
      view: "fabrique",
      badge: "3 / 8",
      title: "Fabrique — Suivi en direct",
      desc: "Suis toutes tes vidéos en cours de fabrication étape par étape (script, voix, décor, montage) et lance plusieurs créations sans perdre le fil.",
      tip: "Astuce : la pilule en haut te ramène ici dès qu'une vidéo tourne."
    },
    {
      view: "montage",
      badge: "4 / 8",
      title: "Montage — Tes vidéos filmées",
      desc: "Importe une vidéo où tu parles pour couper automatiquement les blancs et ajouter sous-titres + zooms, ou découpe une longue vidéo en plusieurs Shorts 9:16.",
      tip: "Astuce : parfait pour recycler tes podcasts, lives ou facecams."
    },
    {
      view: "videos",
      badge: "5 / 8",
      title: "Mes vidéos — Ta bibliothèque 9:16",
      desc: "Parcours tes créations dans la vitrine animée, regarde-les en plein écran une par une, valide celles que tu gardes, demande une retouche IA ou télécharge le MP4.",
      tip: "Astuce : filtre par « À regarder » ou « Validées » pour trier vite."
    },
    {
      view: "auto",
      badge: "6 / 8",
      title: "Publier — Diffusion & calendrier",
      desc: "Connecte YouTube, TikTok, Instagram et Facebook une seule fois, puis publie immédiatement ou programme tes Shorts au jour et à l'heure exacte.",
      tip: "Astuce : tu peux connecter plusieurs comptes et basculer en haut à droite."
    },
    {
      view: "perf",
      badge: "7 / 8",
      title: "Statistiques — Ce qui marche vraiment",
      desc: "Consulte tes vues médianes, ton record, ton engagement, ta durée gagnante et le score /100 de chaque vidéo. Un seul bouton met à jour et analyse ta rétention.",
      tip: "Astuce : clique sur « Refaire la vidéo avec l'IA » sur un ancien short pour l'améliorer."
    },
    {
      view: "plugins",
      badge: "8 / 8",
      title: "Styles & Connexions",
      desc: "Explore les styles visuels prêts à l'emploi (3D, Stickman, Explainer, Dessin animé…) dans Styles, et gère Claude, ElevenLabs, ta licence et tes réseaux dans Connexions.",
      tip: "Astuce : tu pourras relancer ce guide à tout moment depuis Connexions."
    }
  ];

  var data = null, screen = "welcome", tourIdx = 0, bg = null, keyFlow = false, keyBusy = false, toolsTimer = null;

  var CSS = ".ob-bg{z-index:120;transition:background .22s ease}" +
    ".ob-bg.ob-tour-mode{background:rgba(8,10,18,.38);backdrop-filter:none;justify-content:flex-end;padding-right:42px}" +
    "@media(max-width:900px){.ob-bg.ob-tour-mode{justify-content:center;padding-right:16px}}" +
    ".ob-modal{max-width:460px;gap:12px}" +
    ".ob-title{margin:0;font-size:21px;color:var(--ink);letter-spacing:-.02em}" +
    ".ob-body p{margin:0 0 10px;color:var(--ink-2);font-size:14.5px;line-height:1.5}" +
    ".ob-foot{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-top:6px;flex-wrap:wrap}" +
    ".ob-dots{display:flex;gap:5px;margin-bottom:2px}.ob-dot{flex:1;height:4px;border-radius:4px;background:var(--border-hi)}.ob-dot.on{background:var(--accent)}" +
    ".ob-line{display:flex;align-items:center;gap:10px;padding:8px 0;border-top:1px solid var(--border);color:var(--ink);font-size:14px}.ob-line .btn,.ob-line .ob-muted{margin-left:auto}" +
    ".ob-check{width:22px;height:22px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;font-size:12px;background:var(--glass-soft);color:var(--muted)}" +
    ".ob-check.ok{background:var(--ok,#22c55e);color:#fff}.ob-muted{color:var(--muted);font-size:12px}" +
    ".ob-steps{margin:0 0 10px 18px;padding:0;color:var(--ink-2);font-size:14px;line-height:1.6}" +
    ".ob-input{width:100%;box-sizing:border-box;padding:11px 13px;border-radius:12px;border:1px solid var(--border-hi);background:var(--glass-soft);color:var(--ink);font-size:15px}" +
    ".ob-next{display:flex;align-items:center;gap:10px;padding:12px 16px;margin:12px 0;border-radius:16px;border:1px solid var(--border);background:var(--glass)}" +
    ".ob-next-txt{flex:1;color:var(--ink);font-weight:600;font-size:15px}.ob-next-dot{width:8px;height:8px;border-radius:50%;background:var(--accent);flex:none}" +
    ".ob-tour-pills{display:flex;gap:5px;flex-wrap:wrap;margin:2px 0 8px}" +
    ".ob-tour-pill{padding:4px 9px;border-radius:999px;border:1px solid var(--border);background:var(--glass-soft);color:var(--muted);font-size:11.5px;font-weight:600;cursor:pointer;transition:all .16s ease}" +
    ".ob-tour-pill.on{background:var(--accent);border-color:var(--accent);color:#fff}" +
    ".ob-tour-tip{padding:9px 12px;border-radius:12px;background:var(--glass-soft);border:1px solid var(--border);font-size:12.5px;color:var(--ink-2);line-height:1.45}" +
    ".ob-tour-badge{display:inline-block;padding:2px 8px;border-radius:999px;background:var(--accent-soft,rgba(217,38,72,.14));color:var(--accent);font-size:11.5px;font-weight:700;margin-bottom:6px}" +
    ".ob-nav-spotlight{position:relative;z-index:125 !important;background:var(--accent-soft,rgba(217,38,72,.18)) !important;color:var(--ink) !important;box-shadow:0 0 0 2px var(--accent),0 0 22px rgba(217,38,72,.45) !important;border-radius:12px !important;transition:box-shadow .22s ease !important}";
  var st = document.createElement("style"); st.textContent = CSS; document.head.appendChild(st);

  function $(id) { return document.getElementById(id); }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function say(msg) { if (typeof window.toast === "function") window.toast(msg); }
  function step(id) { return ((data && data.steps) || []).filter(function (s) { return s.id === id; })[0] || { done: false, items: [] }; }

  function clearSpotlight() {
    Array.prototype.forEach.call(document.querySelectorAll(".ob-nav-spotlight"), function (el) {
      el.classList.remove("ob-nav-spotlight");
    });
  }

  function highlightSidebar(viewName) {
    clearSpotlight();
    if (!viewName) return;
    var targets = document.querySelectorAll('.app-sidebar [onclick*="showView(\'' + viewName + '\')"]');
    Array.prototype.forEach.call(targets, function (el) {
      el.classList.add("ob-nav-spotlight");
      try { el.scrollIntoView({ behavior: "smooth", block: "nearest" }); } catch (e) {}
    });
    if (typeof window.showView === "function") {
      try { window.showView(viewName); } catch (e) {}
    }
  }

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
      screen = ORDER.indexOf(at) >= 0 ? at : "welcome";
      if (screen === "tour") tourIdx = 0;
      bg.classList.add("open");
      draw();
    };
    data ? go() : api("GET").then(go);
  }

  function close() {
    clearSpotlight();
    if (bg) {
      bg.classList.remove("open");
      bg.classList.remove("ob-tour-mode");
    }
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
    for (var i = 1; i <= 6; i++) out += '<span class="ob-dot' + (i <= idx ? " on" : "") + '"></span>';
    return '<div class="ob-dots">' + out + "</div>";
  }

  function frame(title, body, primary, secondary) {
    var m = bg.querySelector(".ob-modal");
    bg.classList.toggle("ob-tour-mode", screen === "tour");
    if (screen !== "tour") clearSpotlight();
    m.innerHTML = (screen !== "welcome" && screen !== "end" ? dots() : "") +
      '<h2 id="ob-title" class="ob-title">' + title + "</h2>" + '<div class="ob-body">' + body + "</div>" +
      '<div class="ob-foot"><button type="button" class="btn btn-ghost btn-sm" id="ob-sec">' + esc(secondary || "Passer le guide") + "</button>" +
      '<div style="display:flex;gap:8px;align-items:center;" id="ob-foot-right">' +
      (primary ? '<button type="button" class="btn btn-coral" id="ob-pri">' + esc(primary) + "</button>" : "") + "</div></div>";
    $("ob-sec").onclick = screen === "welcome" || screen === "end" ? (screen === "end" ? finish : skipAll) : next;
    return m;
  }

  function okLine(label, ok, extra) {
    return '<div class="ob-line"><span class="ob-check ' + (ok ? "ok" : "") + '">' + (ok ? "✓" : "…") + "</span><span>" + esc(label) + "</span>" + (extra || "") + "</div>";
  }

  function draw() {
    clearTimeout(toolsTimer);
    if (screen === "welcome") {
      frame(
        "Bienvenue sur ClipRoll",
        "<p>Ton studio complet pour créer, monter et publier tes Shorts 9:16.</p>" +
        "<p>On fait un tour rapide de la barre latérale (30 s), puis on vérifie tes connexions.</p>",
        "Faire la visite →",
        "Passer"
      );
      $("ob-pri").onclick = function () { screen = "tour"; tourIdx = 0; draw(); };
    } else if (screen === "tour") drawTour();
    else if (screen === "profile") drawProfile();
    else if (screen === "tools") drawTools();
    else if (screen === "claude") drawClaude();
    else if (screen === "voice") drawVoice();
    else if (screen === "video") drawVideo();
    else if (screen === "social") drawSocial();
    else {
      frame("Tout est prêt !", "<p>Tu connais maintenant chaque espace du studio. L'accueil te guidera toujours sur la prochaine étape.</p>", "Aller à l'accueil", "Fermer");
      $("ob-pri").onclick = finish;
    }
  }

  function drawTour() {
    var stop = TOUR_STOPS[tourIdx] || TOUR_STOPS[0];
    highlightSidebar(stop.view);
    var pills = '<div class="ob-tour-pills">' + TOUR_STOPS.map(function (item, idx) {
      var shortName = item.title.split("—")[0].trim();
      return '<button type="button" class="ob-tour-pill' + (idx === tourIdx ? " on" : "") + '" data-ti="' + idx + '">' + esc(shortName) + "</button>";
    }).join("") + "</div>";

    var isLast = tourIdx >= TOUR_STOPS.length - 1;
    var body =
      '<span class="ob-tour-badge">Visite du studio · ' + esc(stop.badge) + "</span>" +
      pills +
      "<p>" + esc(stop.desc) + "</p>" +
      '<div class="ob-tour-tip">' + esc(stop.tip) + "</div>";

    frame(esc(stop.title), body, isLast ? "Configurer mes outils →" : "Suivant →", "Passer la visite");

    if (tourIdx > 0) {
      var right = $("ob-foot-right");
      var prevBtn = document.createElement("button");
      prevBtn.type = "button";
      prevBtn.className = "btn btn-ghost btn-sm";
      prevBtn.textContent = "← Précédent";
      prevBtn.onclick = function () { tourIdx = Math.max(0, tourIdx - 1); drawTour(); };
      right.insertBefore(prevBtn, right.firstChild);
    }

    $("ob-sec").onclick = function () {
      clearSpotlight();
      screen = "profile";
      draw();
    };
    $("ob-pri").onclick = function () {
      if (isLast) {
        clearSpotlight();
        screen = "profile";
        draw();
      } else {
        tourIdx++;
        drawTour();
      }
    };
    Array.prototype.forEach.call(bg.querySelectorAll(".ob-tour-pill"), function (p) {
      p.onclick = function () {
        tourIdx = parseInt(p.dataset.ti, 10) || 0;
        drawTour();
      };
    });
  }

  function drawProfile() {
    var stPers = (window.ClipoaPersonality && window.ClipoaPersonality.getState && window.ClipoaPersonality.getState()) || {};
    var cur = (stPers.personality) || { mode: "creator" };
    var comps = stPers.competitors || [];
    var isBiz = cur.mode === "business";
    var isPub = !!window.IS_PUBLIC_EDITION;

    var body =
      "<p>Choisis comment ClipRoll doit écrire tes vidéos (modifiable à tout moment dans <b>Créer</b>) :</p>" +
      '<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:10px;">' +
        '<button type="button" class="btn ' + (!isBiz ? "btn-coral" : "btn-ghost") + ' btn-sm" id="ob-mode-creator">🎬 Créateur (normal)</button>' +
        '<button type="button" class="btn ' + (isBiz ? "btn-coral" : "btn-ghost") + ' btn-sm" id="ob-mode-biz">🏢 Entreprise / Marque</button>' +
      '</div>' +
      '<div id="ob-biz-fields" style="display:' + (isBiz ? "flex" : "none") + ';flex-direction:column;gap:7px;margin-bottom:10px;">' +
        '<input type="text" id="ob-biz-name" class="ob-input" style="padding:8px 10px;font-size:13.5px;" value="' + esc(cur.company_name || "") + '" placeholder="Nom de ton entreprise / marque">' +
        '<input type="text" id="ob-biz-ind" class="ob-input" style="padding:8px 10px;font-size:13.5px;" value="' + esc(cur.industry || "") + '" placeholder="Ton métier (ex : Opticien, Garage, Boulangerie…)">' +
        '<input type="text" id="ob-biz-offer" class="ob-input" style="padding:8px 10px;font-size:13.5px;" value="' + esc(cur.offer || "") + '" placeholder="Ton offre à mettre en avant à la fin">' +
      '</div>' +
      (!isPub
        ? '<div style="margin-top:4px;padding-top:8px;border-top:1px solid var(--border);">' +
            '<div style="font-size:12.5px;font-weight:700;color:var(--ink);margin-bottom:5px;">Tes comptes concurrents (facultatif, jusqu\'à 5)</div>' +
            '<textarea id="ob-comp-list" class="ob-input" rows="2" style="padding:8px 10px;font-size:13px;" placeholder="Un @compte ou lien par ligne (ex : @compte1)">' +
              esc(comps.map(function (c) { return c.handle || ""; }).filter(Boolean).join("\n")) +
            '</textarea>' +
          '</div>'
        : "");

    frame("Ta personnalité", body, "Continuer →", "Passer");
    var chosenMode = isBiz ? "business" : "creator";
    var bCr = $("ob-mode-creator"), bBz = $("ob-mode-biz"), fields = $("ob-biz-fields");
    function setMode(m) {
      chosenMode = m;
      bCr.className = "btn " + (m === "creator" ? "btn-coral" : "btn-ghost") + " btn-sm";
      bBz.className = "btn " + (m === "business" ? "btn-coral" : "btn-ghost") + " btn-sm";
      if (fields) fields.style.display = m === "business" ? "flex" : "none";
    }
    bCr.onclick = function () { setMode("creator"); };
    bBz.onclick = function () { setMode("business"); };

    $("ob-pri").onclick = function () {
      var payload = {
        mode: chosenMode,
        company_name: ($("ob-biz-name") || {}).value || "",
        industry: ($("ob-biz-ind") || {}).value || "",
        offer: ($("ob-biz-offer") || {}).value || ""
      };
      var p1 = fetch("/api/personality", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      }).catch(function () {});
      var compEl = $("ob-comp-list");
      var p2 = Promise.resolve();
      if (compEl && !isPub) {
        var list = compEl.value.split(/[\n,]+/).map(function (s) { return s.trim(); }).filter(Boolean).slice(0, 5);
        if (list.length) {
          p2 = fetch("/api/competitors", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ competitors: list })
          }).catch(function () {});
        }
      }
      Promise.all([p1, p2]).then(function () {
        if (window.ClipoaPersonality) window.ClipoaPersonality.refresh();
        screen = firstTodo();
        if (screen === "end") screen = "tools";
        draw();
      });
    };
  }

  function finish() {
    api("POST", { action: "finish" }); close();
    if (typeof window.showView === "function") window.showView("accueil");
  }

  function drawTools() {
    var s = step("tools"), lines = "", installing = false, missingInstallable = 0;
    (s.items || []).forEach(function (t) {
      installing = installing || t.installing;
      if (t.can_install && !t.installing) missingInstallable++;
      var pct = t.progress > 0 && t.progress < 100 ? " " + t.progress + "%" : "";
      var extra = t.can_install && !t.installing
        ? '<button type="button" class="btn btn-ghost btn-xs ob-install" data-tool="' + esc(t.id) + '">Installer</button>'
        : (t.installing ? '<span class="ob-muted">installation…' + pct + '</span>'
          : (t.error ? '<span class="ob-muted" title="' + esc(t.error) + '">erreur</span>' : ""));
      lines += okLine(t.label, t.ok, extra);
    });
    var note = missingInstallable > 0
      ? '<p class="ob-muted" style="margin-top:8px">Téléchargés une seule fois depuis leurs sources officielles (blender.org, FFmpeg, Hugging Face) et vérifiés par empreinte SHA-256.</p>'
      : "";
    var primary = s.done ? "Suivant" : (missingInstallable > 1 ? "Tout installer" : null);
    frame("Les outils", (s.done ? "<p>Tout est installé et prêt à tourner.</p>" : "<p>ClipRoll vérifie ce qu'il faut pour fabriquer tes vidéos.</p>") + lines + note,
      primary, s.done ? null : "Continuer quand même");
    if (s.done) {
      $("ob-pri").onclick = next;
    } else if (missingInstallable > 1) {
      $("ob-pri").onclick = function () {
        $("ob-pri").disabled = true;
        fetch("/api/tools/all/install", { method: "POST" }).then(function () { return api("GET"); }).then(drawTools);
      };
    }
    Array.prototype.forEach.call(bg.querySelectorAll(".ob-install"), function (b) {
      b.onclick = function () {
        b.disabled = true;
        var tool = encodeURIComponent(b.dataset.tool || "blender");
        fetch("/api/tools/" + tool + "/install", { method: "POST" }).then(function () { return api("GET"); }).then(drawTools);
      };
    });
    if (!s.done) toolsTimer = setTimeout(function () { api("GET").then(function () { if (screen === "tools" && bg.classList.contains("open")) drawTools(); }); }, installing ? 4000 : 8000);
  }

  function drawClaude() {
    if (step("claude").done) {
      window.__CLAUDE_CONNECTED__ = true;
      frame("Claude", okLine("Ton compte Claude est connecté.", true), "Suivant", " ");
      $("ob-pri").onclick = next;
      $("ob-sec").style.visibility = "hidden";
      return;
    }
    frame("Connecte Claude",
      "<p>Claude écrit tes scripts et pilote tes vidéos. Il faut un compte Anthropic avec un peu de crédit.</p>" +
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
        if (d.error) return say(d.error);
        keyFlow = false;
        window.__CLAUDE_CONNECTED__ = true;
        say("✓ Claude est connecté");
        return api("GET").then(function () { if (screen === "claude") next(); });
      })
      .catch(function () { keyBusy = false; say("ClipRoll ne répond pas."); });
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
    frame("Une voix plus naturelle ?", "<p>La voix gratuite est déjà prête. ElevenLabs (facultatif) donne une voix encore plus humaine.</p>" + el.portalHtml(),
      "Ouvrir ElevenLabs", "Garder la voix gratuite");
    $("ob-pri").onclick = el.openPortal;
    el.bindPortal(function () { api("GET").then(function () { if (screen === "voice") next(); }); });
  }

  function drawVideo() {
    frame("Ta première vidéo", '<p>Écris ton idée en une phrase. ClipRoll écrit le script, génère la voix et monte le short.</p>' +
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
    var intro = step("video").done ? "<p>Ta vidéo se prépare. En attendant, connecte un réseau pour publier en un clic.</p>"
      : "<p>Connecte un réseau pour publier ou programmer en un clic.</p>";
    frame("Publier", intro + lines, s.done ? "Suivant" : null, s.done ? null : (any ? "Plus tard" : "Continuer"));
    if (s.done) $("ob-pri").onclick = next;
    Array.prototype.forEach.call(bg.querySelectorAll(".ob-social"), function (b) {
      b.onclick = function () {
        if (typeof window.connectSocialOAuth === "function") window.connectSocialOAuth(b.dataset.net, "reglages", true);
      };
    });
  }

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      if (bg && bg.classList.contains("open")) close();
      else clearSpotlight();
      return;
    }
    if (!bg || !bg.classList.contains("open")) return;
    if (screen === "tour") {
      if (e.key === "ArrowRight") {
        if (tourIdx < TOUR_STOPS.length - 1) { tourIdx++; drawTour(); }
      } else if (e.key === "ArrowLeft") {
        if (tourIdx > 0) { tourIdx--; drawTour(); }
      }
    }
  }, true);

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
