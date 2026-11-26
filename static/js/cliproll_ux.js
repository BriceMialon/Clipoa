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

  // Affichage confié aux notifications empilées (static/js/cliproll_toast.js).
  function show(msg, label, run, ms, type) {
    if (typeof window.__crToast !== "function") return;
    return window.__crToast(msg, type || null, { action: (label && run) ? { label: label, run: run } : null, ms: ms });
  }

  // Remplace toast() : même usage, mais une erreur connue reçoit son bouton.
  window.toast = function (msg, type) {
    var t = plain(msg);
    if (!/^\s*(✓|✅|🎉)/.test(String(msg)) && PROBLEM.test(t)) {
      for (var i = 0; i < FIXES.length; i++) {
        if (FIXES[i].re.test(t)) return show(msg, FIXES[i].label, FIXES[i].run, null, type || "error");
      }
    }
    return show(msg, null, null, null, type);
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

})();
