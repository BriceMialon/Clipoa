/* Notifications empilées ClipRoll : toast(message, type?)
   type = 'success' | 'error' | 'info' ; deviné si absent.
   opts = { action: { label, run }, ms } : bouton qui corrige (utilisé par cliproll_ux.js).
   3 visibles au maximum, pause au survol, bouton Fermer, erreurs lues
   immédiatement par les lecteurs d'écran. Aucune dépendance. */
(function () {
  "use strict";
  var MAX = 3;
  var ICONS = {
    success: '<path d="M5 12l5 5l10 -10"/>',
    error: '<path d="M12 9v4"/><path d="M12 16h.01"/><path d="M10.24 3.96l-8.1 13.54a2 2 0 0 0 1.71 3h16.3a2 2 0 0 0 1.71 -3l-8.1 -13.54a2 2 0 0 0 -3.52 0z"/>',
    info: '<path d="M12 8h.01"/><path d="M11 12h1v4h1"/><path d="M12 3a9 9 0 1 0 0 18a9 9 0 0 0 0 -18z"/>'
  };
  var ERR_RE = /^(❌|⚠️?\s*)|\b(erreur|échec|echec|impossible|invalide|introuvable|manquant|refus|expir|bloqu|indisponible|error|failed)/i;

  function guessType(msg) {
    if (/^\s*✓/.test(msg)) return "success";
    if (ERR_RE.test(msg)) return "error";
    return "info";
  }

  function stack() {
    var s = document.getElementById("toast-stack");
    if (!s) {
      s = document.createElement("div");
      s.id = "toast-stack";
      document.body.appendChild(s);
    }
    return s;
  }

  function dismiss(el) {
    if (!el || el._gone) return;
    el._gone = true;
    clearTimeout(el._t);
    el.classList.remove("show");
    el.classList.add("hide");
    setTimeout(function () { if (el.parentNode) el.parentNode.removeChild(el); }, 220);
  }

  function toast(msg, type, opts) {
    opts = opts || {};
    msg = msg == null ? "" : String(msg);
    type = type || guessType(msg);
    var text = msg.replace(/^\s*(✓|❌|⚠️?)\s*/, "").trim() || msg;
    var s = stack();

    // Même message déjà affiché : on le relance au lieu de l'empiler.
    var kids = s.querySelectorAll(".cr-toast:not(.hide)");
    for (var i = 0; i < kids.length; i++) {
      if (kids[i]._text === text && !opts.action) { arm(kids[i]); return kids[i]; }
    }

    var el = document.createElement("div");
    el.className = "cr-toast " + type;
    el.setAttribute("role", type === "error" ? "alert" : "status");
    el.setAttribute("aria-live", type === "error" ? "assertive" : "polite");
    el._text = text;
    el._ms = opts.ms || Math.min(9000, (type === "error" ? 6000 : 3000) + text.length * 35);
    if (opts.action) el._ms = Math.max(el._ms, 7000);
    el.innerHTML = '<svg class="cr-toast-ico" viewBox="0 0 24 24" aria-hidden="true">' + ICONS[type] + "</svg>" +
      '<div class="cr-toast-msg"></div>' +
      '<button type="button" class="cr-toast-x" aria-label="Fermer la notification">✕</button>';
    el.querySelector(".cr-toast-msg").textContent = text;
    if (opts.action && opts.action.label && typeof opts.action.run === "function") {
      var b = document.createElement("button");
      b.type = "button"; b.className = "cr-toast-action"; b.textContent = opts.action.label;
      b.addEventListener("click", function () { dismiss(el); opts.action.run(); });
      el.insertBefore(b, el.querySelector(".cr-toast-x"));
    }
    el.querySelector(".cr-toast-x").addEventListener("click", function () { dismiss(el); });
    el.addEventListener("mouseenter", function () { clearTimeout(el._t); });
    el.addEventListener("mouseleave", function () { arm(el); });
    el.addEventListener("focusin", function () { clearTimeout(el._t); });
    el.addEventListener("focusout", function () { arm(el); });

    s.appendChild(el);
    var live = s.querySelectorAll(".cr-toast:not(.hide)");
    for (var j = 0; j < live.length - MAX; j++) dismiss(live[j]);
    requestAnimationFrame(function () { requestAnimationFrame(function () { el.classList.add("show"); }); });
    arm(el);
    return el;
  }

  function arm(el) {
    clearTimeout(el._t);
    el._t = setTimeout(function () { dismiss(el); }, el._ms);
  }

  window.__crToast = toast;
  window.toast = toast;
  window.toastSuccess = function (m) { return toast(m, "success"); };
  window.toastError = function (m) { return toast(m, "error"); };
})();
