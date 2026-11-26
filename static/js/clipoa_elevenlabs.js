// Connexion ElevenLabs guidée + changement de compte en un clic.
// ElevenLabs n'a pas d'OAuth pour les apps tierces : on ouvre la page des clés, puis la clé copiée
// est lue dans le presse-papiers au retour sur ClipRoll (ou collée). Chaque compte branché est mémorisé.
(function () {
  "use strict";
  var KEY_RE = /sk_[A-Za-z0-9]{32,}/;
  var KEYS_URL = "https://elevenlabs.io/app/developers";
  var bg = null, waiting = false, busy = false, onDone = null;

  function $(id) { return document.getElementById(id); }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function say(m) { if (typeof window.toast === "function") window.toast(m); }
  function json(url, body) {
    return fetch(url, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : { cache: "no-store" })
      .then(function (r) { return r.json(); }).catch(function () { return { error: "ClipRoll ne répond pas." }; });
  }

  // Étapes réutilisées par le guide de premier lancement.
  function portalHtml() {
    return '<ol class="ob-steps"><li>Clique sur « Ouvrir ElevenLabs » et connecte-toi.</li>' +
      '<li>Crée une clé (« Create API key ») et copie-la.</li><li>Reviens ici : c\'est automatique.</li></ol>' +
      '<input type="password" class="ob-input" id="el-portal-key" placeholder="Ou colle ta clé ici (sk_…)" autocomplete="off">';
  }
  function bindPortal(done) {
    onDone = done || null;
    var inp = $("el-portal-key");
    if (inp) inp.oninput = function () { var m = inp.value.match(KEY_RE); if (m) save(m[0]); };
  }
  function openPortal() { window.open(KEYS_URL, "_blank", "noopener"); waiting = true; }

  function save(key) {
    if (busy) return;
    busy = true; say("Test de la clé…");
    json("/api/elevenlabs/connect", { api_key: key, enabled: true }).then(function (d) {
      busy = false;
      if (d.error) return say("❌ " + d.error);
      waiting = false; say("✓ ElevenLabs est connecté");
      if (onDone) onDone(d); else location.reload();
    });
  }

  window.addEventListener("focus", function () {
    if (!waiting || busy || !navigator.clipboard || !navigator.clipboard.readText) return;
    navigator.clipboard.readText().then(function (t) {
      var m = String(t || "").match(KEY_RE);
      if (m) { var inp = $("el-portal-key"); if (inp) inp.value = m[0]; save(m[0]); }
    }).catch(function () { /* lecture refusée : l'utilisateur colle à la main */ });
  });

  // ---------- Fenêtre Connexions : comptes + ajout ----------
  function ensure() {
    if (bg) return;
    bg = document.createElement("div");
    bg.className = "modal-bg ob-bg"; bg.id = "modal-el-portal";
    bg.innerHTML = '<div class="modal ob-modal" role="dialog" aria-modal="true"></div>';
    bg.onclick = function (e) { if (e.target === bg) close(); };
    document.body.appendChild(bg);
  }
  function close() { if (bg) bg.classList.remove("open"); waiting = false; }

  function open() {
    ensure(); bg.classList.add("open");
    var m = bg.querySelector(".modal");
    m.innerHTML = '<h2 class="ob-title">ElevenLabs</h2><div class="ob-body"><p>Chargement…</p></div>';
    json("/api/elevenlabs/accounts").then(function (d) { draw((d && d.accounts) || []); });
  }

  function draw(accounts) {
    var m = bg.querySelector(".modal"), list = "";
    accounts.forEach(function (a) {
      list += '<div class="ob-line"><span class="ob-check ' + (a.active ? "ok" : "") + '">' + (a.active ? "✓" : "") + "</span><span>" + esc(a.label) + "</span>" +
        (a.active ? '<span class="ob-muted">actif</span>' : '<button type="button" class="btn btn-ghost btn-xs el-sw" data-id="' + esc(a.id) + '">Utiliser</button>') + "</div>";
    });
    var adding = !accounts.length;
    m.innerHTML = '<h2 class="ob-title">' + (adding ? "Connecte ElevenLabs" : "Tes comptes ElevenLabs") + "</h2>" +
      '<div class="ob-body">' + (adding ? "<p>Pour une voix plus naturelle. Il faut un compte ElevenLabs.</p>" + portalHtml() : list) + "</div>" +
      '<div class="ob-foot"><button type="button" class="btn btn-ghost btn-sm" id="el-close">Fermer</button>' +
      '<button type="button" class="btn btn-coral" id="el-main">' + (adding ? "Ouvrir ElevenLabs" : "Ajouter un compte") + "</button></div>";
    $("el-close").onclick = close;
    if (adding) { bindPortal(null); $("el-main").onclick = openPortal; }
    else $("el-main").onclick = function () { draw([]); };
    Array.prototype.forEach.call(m.querySelectorAll(".el-sw"), function (b) {
      b.onclick = function () {
        b.disabled = true; say("Changement de compte…");
        json("/api/elevenlabs/switch", { id: b.dataset.id }).then(function (d) {
          if (d.error) { b.disabled = false; return say("❌ " + d.error); }
          say("✓ Compte changé"); location.reload();
        });
      };
    });
  }

  window.ClipoaEleven = { open: open, portalHtml: portalHtml, bindPortal: bindPortal, openPortal: openPortal };
})();
