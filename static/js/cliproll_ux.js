// Parcours mâché : messages d'erreur avec le bouton qui corrige, style choisi d'après l'idée.
(function () {
  "use strict";

  function guide(at) { if (window.ClipoaOnboarding) window.ClipoaOnboarding.show(at); }
  function eleven() { if (window.ClipoaEleven) window.ClipoaEleven.open(); }

  // Message (en minuscules, sans accents) → bouton qui règle le problème.
  var FIXES = [
    { re: /elevenlabs/, label: "Connecter ElevenLabs", run: eleven },
    { re: /claude|anthropic|connecte une ia|cle api/, label: "Connecter Claude", run: function () { guide("claude"); } },
    { re: /blender|3d n.est pas|outil/, label: "Installer", run: function () { guide("tools"); } },
    { re: /youtube|tiktok|reseau|plateforme/, label: "Connecter", run: function () { guide("social"); } },
    { re: /pas encore de video/, label: "Fabriquer", run: function () {
        if (window.showView) window.showView("accueil");
        var i = document.getElementById("home-quick-input"); if (i) i.focus();
      } },
    { re: /quota|limite|credit/, label: "Voir", run: function () { if (window.showView) window.showView("reglages"); } }
  ];
  var PROBLEM = /❌|⚠|impossible|manque|refus|invalide|erreur|echou|indisponible|branche|connecte|installe|pas encore|aucun|epuise|atteint/;

  function plain(s) { return String(s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, ""); }

  var timer = null;
  function show(msg, label, run, ms) {
    var el = document.getElementById("toast");
    if (!el) return;
    el.textContent = msg;
    if (label && run) {
      var b = document.createElement("button");
      b.type = "button"; b.textContent = label; b.className = "toast-fix";
      b.onclick = function () { el.classList.remove("show"); run(); };
      el.appendChild(b);
    }
    el.classList.toggle("has-fix", !!(label && run));
    el.classList.add("show");
    clearTimeout(timer);
    timer = setTimeout(function () { el.classList.remove("show", "has-fix"); }, ms || (label ? 7000 : 2800));
  }

  // Remplace toast() : même usage, mais une erreur connue reçoit son bouton.
  window.toast = function (msg) {
    var t = plain(msg);
    if (!/^\s*(✓|✅|🎉)/.test(String(msg)) && PROBLEM.test(t)) {
      for (var i = 0; i < FIXES.length; i++) {
        if (FIXES[i].re.test(t)) return show(msg, FIXES[i].label, FIXES[i].run);
      }
    }
    show(msg);
  };
  window.toastAction = function (msg, label, run) { show(msg, label, run); };

  // Style d'après l'idée, seulement si l'utilisateur n'en a pas choisi un lui-même.
  window.ClipoaUX = {
    autoStyle: function (topic) {
      if (window.__styleChosenByUser || !String(topic || "").trim()) return Promise.resolve(null);
      if (typeof window.refUrlLocksStyle === "function" && window.refUrlLocksStyle()) return Promise.resolve(null);
      return fetch("/api/auto-style?topic=" + encodeURIComponent(String(topic).slice(0, 500)), { cache: "no-store" })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (!d || !d.plugin_id || typeof window.selectStylePlaque !== "function") return null;
          window.selectStylePlaque("plugin:" + d.plugin_id);
          show("Style choisi pour toi : " + d.name + " (" + d.reason + ")", null, null, 4000);
          return d;
        })
        .catch(function () { return null; });
    }
  };

  var st = document.createElement("style");
  st.textContent = "#toast.has-fix{pointer-events:auto;display:flex;align-items:center;gap:12px;padding:8px 8px 8px 20px}" +
    ".toast-fix{border:0;border-radius:999px;padding:6px 14px;font-weight:700;font-size:13px;cursor:pointer;background:var(--accent);color:#fff}";
  document.head.appendChild(st);
})();
