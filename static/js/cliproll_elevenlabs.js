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
      if (d.error) return say(d.error);
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
      (adding ? "" : '<button type="button" class="btn btn-ghost btn-sm" id="el-roster">Mes voix validées</button>') +
      '<button type="button" class="btn btn-coral" id="el-main">' + (adding ? "Ouvrir ElevenLabs" : "Ajouter un compte") + "</button></div>";
    $("el-close").onclick = close;
    if (adding) { bindPortal(null); $("el-main").onclick = openPortal; }
    else { $("el-main").onclick = function () { draw([]); }; $("el-roster").onclick = roster; }
    Array.prototype.forEach.call(m.querySelectorAll(".el-sw"), function (b) {
      b.onclick = function () {
        b.disabled = true; say("Changement de compte…");
        json("/api/elevenlabs/switch", { id: b.dataset.id }).then(function (d) {
          if (d.error) { b.disabled = false; return say(d.error); }
          say("✓ Compte changé"); location.reload();
        });
      };
    });
  }

  // ---------- Voix validées : l'utilisateur écoute ses voix et dit à quoi chacune sert ----------
  // Le casting les prend en priorité, mais seulement pour ces emplois (une voix de conteur ne fait pas un tuto).
  function rosterCss() {
    if ($("el-roster-css")) return;
    var st = document.createElement("style"); st.id = "el-roster-css";
    st.textContent = ".el-voice{padding:4px 0 8px}.el-roles{display:flex;flex-wrap:wrap;gap:6px}" +
      ".el-role{font-size:12px;padding:3px 8px;border:1px solid var(--border);border-radius:999px;cursor:pointer;color:var(--ink)}" +
      ".el-role input{margin:0 4px 0 0;vertical-align:middle}.el-play{margin-right:6px}";
    document.head.appendChild(st);
  }
  function roster() {
    ensure(); rosterCss(); bg.classList.add("open");
    var m = bg.querySelector(".modal");
    m.innerHTML = '<h2 class="ob-title">Mes voix validées</h2><div class="ob-body"><p>Chargement des voix…</p></div>';
    Promise.all([json("/api/elevenlabs/roster"), json("/api/elevenlabs/voices")]).then(function (r) {
      var cfg = r[0] || {}, voices = (r[1] && r[1].voices) || [], roles = cfg.roles || {};
      var chosen = {};
      (cfg.roster || []).forEach(function (v) { chosen[v.voice_id] = v; });
      (cfg.roster || []).forEach(function (v) {  // voix validée absente du compte : on la garde visible
        if (!voices.some(function (x) { return x.voice_id === v.voice_id; })) voices.unshift({ voice_id: v.voice_id, name: v.name || v.voice_id });
      });
      var rows = voices.map(function (v) {
        var cur = (chosen[v.voice_id] || {}).roles || [];
        var chips = Object.keys(roles).map(function (k) {
          return '<label class="el-role"><input type="checkbox" data-v="' + esc(v.voice_id) + '" data-r="' + esc(k) + '"' +
            (cur.indexOf(k) >= 0 ? " checked" : "") + "> " + esc(roles[k]) + "</label>";
        }).join("");
        var play = v.preview_url ? '<button type="button" class="btn btn-ghost btn-xs el-play" data-u="' + esc(v.preview_url) + '">▶</button>' : "";
        return '<div class="el-voice" data-v="' + esc(v.voice_id) + '" data-n="' + esc(v.name) + '"><div class="ob-line">' + play +
          "<strong>" + esc(v.name) + '</strong><span class="ob-muted">' + esc(v.category || "") + '</span></div><div class="el-roles">' + chips + "</div></div>";
      }).join("");
      m.innerHTML = '<h2 class="ob-title">Mes voix validées</h2><div class="ob-body">' +
        "<p>Coche à quoi sert chaque voix que tu trouves bonne. ClipRoll la prendra en priorité, mais seulement pour ces emplois : " +
        "une voix de conteur ne fera pas un tuto ni un sketch.</p>" +
        (cfg.library_blocked ? '<p class="ob-muted">⚠️ ElevenLabs a refusé récemment les voix de sa bibliothèque (compte gratuit ?) : ' +
          "valide ici des voix de ton compte.</p>" : "") +
        '<label class="ob-line">Vitesse de la voix <input type="number" id="el-speed" min="0.95" max="1.15" step="0.01" value="' +
        esc((cfg.speed || 1.08).toFixed(2)) + '" style="width:5em"> <span class="ob-muted">1,08 = un peu plus vif que normal</span></label>' +
        '<div class="el-voices" style="max-height:52vh;overflow:auto">' + (rows || "<p>Aucune voix sur ce compte.</p>") + "</div></div>" +
        '<div class="ob-foot"><button type="button" class="btn btn-ghost btn-sm" id="el-back">Retour</button>' +
        '<button type="button" class="btn btn-coral" id="el-save">Enregistrer</button></div>';
      var audio = null;
      Array.prototype.forEach.call(m.querySelectorAll(".el-play"), function (b) {
        b.onclick = function () { if (audio) audio.pause(); audio = new Audio(b.dataset.u); audio.play(); };
      });
      $("el-back").onclick = open;
      $("el-save").onclick = function () {
        var out = [];
        Array.prototype.forEach.call(m.querySelectorAll(".el-voice"), function (row) {
          var rs = Array.prototype.filter.call(row.querySelectorAll("input:checked"), function () { return true; })
            .map(function (i) { return i.dataset.r; });
          if (rs.length) out.push({ voice_id: row.dataset.v, name: row.dataset.n, roles: rs });
        });
        json("/api/elevenlabs/roster", { roster: out, speed: parseFloat($("el-speed").value) }).then(function (d) {
          if (d.error) return say(d.error);
          say("✓ " + out.length + " voix validée" + (out.length > 1 ? "s" : ""));
          if (audio) audio.pause();
          open();
        });
      };
    });
  }

  window.ClipoaEleven = { open: open, roster: roster, portalHtml: portalHtml, bindPortal: bindPortal, openPortal: openPortal };
})();
