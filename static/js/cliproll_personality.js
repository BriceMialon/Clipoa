// Personnalité de création (Créateur vs Entreprise/Marque) + Suivi des 5 comptes concurrents (Outliers >= 2×).
(function () {
  "use strict";

  var _state = { personality: null, angles: [], examples: [], custom: [], activeCustom: null, editingCustom: null, competitors: [] };

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function say(msg) {
    if (typeof window.toast === "function") window.toast(msg);
  }

  function fmtViews(n) {
    var v = Number(n || 0);
    if (v >= 1000000) return (v / 1000000).toFixed(1).replace(".0", "") + " M";
    if (v >= 1000) return (v / 1000).toFixed(1).replace(".0", "") + " k";
    return String(v);
  }

  // ---------- Styles légers ----------
  var CSS =
    ".cr-pers-box{margin-bottom:14px;padding:14px 16px;border-radius:18px;background:var(--glass-soft);border:1px solid var(--border);display:flex;flex-direction:column;gap:10px}" +
    ".cr-pers-top{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap}" +
    ".cr-pers-seg{display:inline-flex;padding:3px;border-radius:999px;background:var(--bg-elev);border:1px solid var(--border);gap:3px}" +
    ".cr-pers-btn{padding:6px 13px;border-radius:999px;border:0;background:transparent;color:var(--muted);font-size:12.5px;font-weight:700;cursor:pointer;transition:all .16s ease}" +
    ".cr-pers-btn.on{background:var(--accent);color:#fff}" +
    ".cr-pers-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:8px}" +
    ".cr-pers-custom-form{display:flex;flex-direction:column;gap:8px;padding:12px;border-radius:14px;background:var(--bg-elev);border:1px solid var(--border)}" +
    ".cr-pers-summary{padding:10px 12px;border-radius:14px;background:var(--bg-elev);border:1px solid var(--border);display:flex;flex-direction:column;gap:6px}" +
    ".cr-pers-angles{display:flex;gap:6px;flex-wrap:wrap;align-items:center}" +
    ".cr-comp-card{margin-bottom:16px}" +
    ".cr-comp-inputs{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:8px;margin-top:10px}" +
    ".cr-comp-results{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px;margin-top:14px}" +
    ".cr-comp-item{padding:12px 14px;border-radius:16px;background:var(--glass-soft);border:1px solid var(--border);display:flex;flex-direction:column;gap:8px}" +
    ".cr-comp-ratio{display:inline-flex;align-items:center;padding:2px 8px;border-radius:999px;background:var(--accent-soft,rgba(217,38,72,.14));color:var(--accent);font-weight:800;font-size:12px}";
  var st = document.createElement("style");
  st.textContent = CSS;
  document.head.appendChild(st);

  function applyPersonalityResponse(d) {
    _state.personality = d.personality || { mode: "creator" };
    _state.angles = d.angles || [];
    if (d.examples) _state.examples = d.examples;
    if (d.custom_personalities) _state.custom = d.custom_personalities;
    _state.activeCustom = d.active_custom || null;
    renderCreerPersonality();
    renderSettingsPersonality();
  }

  async function loadPersonality() {
    try {
      var r = await fetch("/api/personality", { cache: "no-store" });
      if (!r.ok) return;
      applyPersonalityResponse(await r.json());
    } catch (e) {}
  }

  async function savePersonality(patch) {
    try {
      var r = await fetch("/api/personality", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      });
      var d = await r.json();
      if (d.error) return say(d.error);
      applyPersonalityResponse(d);
      return d.personality;
    } catch (e) {
      say("Impossible d'enregistrer la personnalité.");
    }
  }

  async function saveCustomPersonality(payload) {
    try {
      var r = await fetch("/api/personalities", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      var d = await r.json();
      if (!r.ok || d.error) return say(d.error || "Erreur d'enregistrement.");
      _state.editingCustom = null;
      applyPersonalityResponse(d);
      say("Personnalité « " + (d.item && d.item.name ? d.item.name : "") + " » enregistrée et activée.");
      return d.item;
    } catch (e) {
      say("Impossible d'enregistrer cette personnalité.");
    }
  }

  async function deleteCustomPersonality(pid) {
    try {
      var r = await fetch("/api/personalities/" + encodeURIComponent(pid), { method: "DELETE" });
      var d = await r.json();
      if (!r.ok) return say(d.error || "Suppression impossible.");
      _state.editingCustom = null;
      applyPersonalityResponse(d);
      say("Personnalité supprimée.");
    } catch (e) {
      say("Suppression impossible.");
    }
  }

  function renderCreerPersonality() {
    var topicEl = document.getElementById("main-topic");
    if (!topicEl) return;
    var host = document.getElementById("cr-creer-personality");
    if (!host) {
      host = document.createElement("div");
      host.id = "cr-creer-personality";
      host.className = "cr-pers-box";
      var targetParent = topicEl.parentElement;
      if (targetParent) targetParent.insertBefore(host, topicEl);
    }
    var p = _state.personality || { mode: "creator" };
    var isBiz = p.mode === "business";
    var isCustom = p.mode === "custom" && !!_state.activeCustom;
    var ac = _state.activeCustom;
    var exBtns = (_state.examples || []).map(function (ex, idx) {
      return '<button type="button" class="chip" data-ex="' + idx + '">' + esc(ex.label) + "</button>";
    }).join("");
    var angleBtns = (_state.angles || []).map(function (a, idx) {
      return '<button type="button" class="btn btn-ghost btn-xs" data-angle="' + idx + '">' + esc(a.label) + "</button>";
    }).join("");
    var customSegBtns = (_state.custom || []).map(function (cp) {
      var on = isCustom && ac && ac.id === cp.id;
      return '<button type="button" class="cr-pers-btn' + (on ? " on" : "") + '" data-cid="' + esc(cp.id) + '">' + esc(cp.name) + "</button>";
    }).join("");

    var bodyHtml = "";
    if (_state.editingCustom) {
      var ed = _state.editingCustom;
      var anglesText = (ed.angles || []).map(function (a) {
        return (a.label ? a.label + " : " : "") + (a.topic || "");
      }).join("\n");
      bodyHtml =
        '<div class="cr-pers-custom-form">' +
          '<div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;">' +
            '<span style="font-size:13px;font-weight:700;color:var(--ink);">' + (ed.id ? "Modifier la personnalité « " + esc(ed.name) + " »" : "Nouvelle personnalité de création") + "</span>" +
            '<button type="button" class="btn btn-ghost btn-xs" id="cr-cp-cancel">Fermer</button>' +
          "</div>" +
          '<div class="cr-pers-grid">' +
            '<input type="text" id="cr-cp-name" class="input-sm" value="' + esc(ed.name || "") + '" placeholder="Nom (ex : Ma Marque, Coach Sport…)">' +
            '<input type="text" id="cr-cp-aud" class="input-sm" value="' + esc(ed.audience || "") + '" placeholder="Public cible (ex : entrepreneurs, créateurs…)">' +
            '<input type="text" id="cr-cp-tone" class="input-sm" value="' + esc(ed.tone || "") + '" placeholder="Ton & style (ex : direct, rythmé, sans blabla)">' +
            '<input type="text" id="cr-cp-cta" class="input-sm" value="' + esc(ed.cta || "") + '" placeholder="Appel à l\'action final (ex : lien en bio)">' +
          "</div>" +
          '<textarea id="cr-cp-mission" class="input-sm" rows="2" placeholder="Objectif / Produit / Promesse (à quoi sert ton projet ou ton offre)">' + esc(ed.mission || "") + "</textarea>" +
          '<textarea id="cr-cp-keys" class="input-sm" rows="2" placeholder="Infos clés à glisser dans les vidéos (dates, chiffres, offre, bénéfices…)">' + esc(ed.key_points || "") + "</textarea>" +
          '<input type="text" id="cr-cp-rules" class="input-sm" value="' + esc(ed.rules || "") + '" placeholder="Règles & interdits (ex : hook en 1.5s, pas de jargon)">' +
          '<textarea id="cr-cp-angles" class="input-sm" rows="3" placeholder="Idées de vidéos en 1 clic (une par ligne, format Titre : Sujet)">' + esc(anglesText) + "</textarea>" +
          '<div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;">' +
            (ed.id ? '<button type="button" class="btn btn-ghost btn-xs" id="cr-cp-del" style="color:var(--danger,#ef4444);">Supprimer</button>' : "<span></span>") +
            '<button type="button" class="btn btn-coral btn-xs" id="cr-cp-save">Enregistrer cette personnalité</button>' +
          "</div>" +
        "</div>";
    } else if (isCustom && ac) {
      bodyHtml =
        '<div class="cr-pers-summary">' +
          '<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;flex-wrap:wrap;">' +
            '<div>' +
              '<div style="font-size:13.5px;font-weight:800;color:var(--ink);">' + esc(ac.name) + "</div>" +
              (ac.mission ? '<div style="font-size:12px;color:var(--muted);margin-top:2px;line-height:1.4;">' + esc(ac.mission) + "</div>" : "") +
              (ac.key_points ? '<div style="font-size:11.5px;color:var(--ink-2);margin-top:4px;line-height:1.4;"><b>Infos clés :</b> ' + esc(ac.key_points) + "</div>" : "") +
            "</div>" +
            '<button type="button" class="btn btn-ghost btn-xs" id="cr-cp-edit-active">Modifier</button>' +
          "</div>" +
          (angleBtns
            ? '<div class="cr-pers-angles"><span style="font-size:11.5px;color:var(--muted);font-weight:600;">Idées prêtes :</span>' + angleBtns + "</div>"
            : "") +
        "</div>";
    } else if (isBiz) {
      bodyHtml =
        '<div class="cr-pers-grid">' +
          '<input type="text" id="cr-p-name" class="input-sm" value="' + esc(p.company_name || "") + '" placeholder="Nom de ton entreprise / marque">' +
          '<input type="text" id="cr-p-ind" class="input-sm" value="' + esc(p.industry || "") + '" placeholder="Métier / secteur (ex : Opticien, Garage…)">' +
          '<input type="text" id="cr-p-offer" class="input-sm" value="' + esc(p.offer || "") + '" placeholder="Offre à mettre en avant (ex : diagnostic offert)">' +
          '<input type="text" id="cr-p-cta" class="input-sm" value="' + esc(p.cta || "") + '" placeholder="Appel à l\'action (ex : Passe en boutique)">' +
        "</div>" +
        '<div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;">' +
          '<div style="display:flex;gap:5px;flex-wrap:wrap;align-items:center;"><span style="font-size:11.5px;color:var(--muted);">Exemples :</span>' + exBtns + "</div>" +
          '<button type="button" class="btn btn-primary btn-xs" id="cr-p-save">Enregistrer la fiche</button>' +
        "</div>" +
        '<div class="cr-pers-angles">' +
          '<span style="font-size:11.5px;color:var(--muted);font-weight:600;">Angles 1-clic :</span>' + angleBtns +
        "</div>";
    }

    host.innerHTML =
      '<div class="cr-pers-top">' +
        '<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">' +
          '<span style="font-size:12.5px;font-weight:700;color:var(--ink);">Personnalité</span>' +
          '<div class="cr-pers-seg" role="group" aria-label="Personnalité de création">' +
            '<button type="button" class="cr-pers-btn' + (!isBiz && !isCustom ? " on" : "") + '" data-pmode="creator">Créateur</button>' +
            '<button type="button" class="cr-pers-btn' + (isBiz ? " on" : "") + '" data-pmode="business">Entreprise</button>' +
            customSegBtns +
          "</div>" +
          '<button type="button" class="btn btn-ghost btn-xs" id="cr-cp-new">+ Créer</button>' +
        "</div>" +
        '<span style="font-size:12px;color:var(--muted);">' +
          (isCustom && ac
            ? "Personnalité active : " + esc(ac.name)
            : (isBiz
              ? "Structure 3 temps : geste du quotidien → conseil métier → offre à la fin."
              : "Mode libre : crée des shorts sur n'importe quel sujet.")) +
        "</span>" +
      "</div>" +
      bodyHtml;

    Array.prototype.forEach.call(host.querySelectorAll("[data-pmode]"), function (b) {
      b.onclick = function () {
        _state.editingCustom = null;
        var mode = b.dataset.pmode;
        savePersonality({ mode: mode, active_custom_id: "" }).then(function () {
          say(mode === "business" ? "Mode Entreprise activé." : "Mode Créateur activé.");
        });
      };
    });

    Array.prototype.forEach.call(host.querySelectorAll("[data-cid]"), function (b) {
      b.onclick = function () {
        _state.editingCustom = null;
        var cid = b.dataset.cid;
        savePersonality({ mode: "custom", active_custom_id: cid }).then(function () {
          say("Personnalité « " + b.textContent.trim() + " » activée.");
        });
      };
    });

    var newBtn = host.querySelector("#cr-cp-new");
    if (newBtn) {
      newBtn.onclick = function () {
        _state.editingCustom = { name: "", mission: "", audience: "", tone: "", key_points: "", cta: "", rules: "", angles: [] };
        renderCreerPersonality();
      };
    }

    var editActiveBtn = host.querySelector("#cr-cp-edit-active");
    if (editActiveBtn && ac) {
      editActiveBtn.onclick = function () {
        _state.editingCustom = Object.assign({}, ac);
        renderCreerPersonality();
      };
    }

    var cancelBtn = host.querySelector("#cr-cp-cancel");
    if (cancelBtn) {
      cancelBtn.onclick = function () {
        _state.editingCustom = null;
        renderCreerPersonality();
      };
    }

    var saveCustomBtn = host.querySelector("#cr-cp-save");
    if (saveCustomBtn && _state.editingCustom) {
      saveCustomBtn.onclick = function () {
        var ed = _state.editingCustom;
        saveCustomPersonality({
          id: ed.id || "",
          name: (host.querySelector("#cr-cp-name") || {}).value || "",
          mission: (host.querySelector("#cr-cp-mission") || {}).value || "",
          audience: (host.querySelector("#cr-cp-aud") || {}).value || "",
          tone: (host.querySelector("#cr-cp-tone") || {}).value || "",
          key_points: (host.querySelector("#cr-cp-keys") || {}).value || "",
          cta: (host.querySelector("#cr-cp-cta") || {}).value || "",
          rules: (host.querySelector("#cr-cp-rules") || {}).value || "",
          angles: (host.querySelector("#cr-cp-angles") || {}).value || "",
          private_owner: !!ed.private_owner,
          activate: true,
        });
      };
    }

    var delCustomBtn = host.querySelector("#cr-cp-del");
    if (delCustomBtn && _state.editingCustom && _state.editingCustom.id) {
      delCustomBtn.onclick = function () {
        deleteCustomPersonality(_state.editingCustom.id);
      };
    }

    var saveBtn = host.querySelector("#cr-p-save");
    if (saveBtn) {
      saveBtn.onclick = function () {
        savePersonality({
          mode: "business",
          company_name: (host.querySelector("#cr-p-name") || {}).value || "",
          industry: (host.querySelector("#cr-p-ind") || {}).value || "",
          offer: (host.querySelector("#cr-p-offer") || {}).value || "",
          cta: (host.querySelector("#cr-p-cta") || {}).value || "",
        }).then(function () { say("Fiche entreprise enregistrée."); });
      };
    }

    Array.prototype.forEach.call(host.querySelectorAll("[data-ex]"), function (b) {
      b.onclick = function () {
        var ex = _state.examples[parseInt(b.dataset.ex, 10)];
        if (!ex) return;
        savePersonality({
          mode: "business",
          company_name: ex.company_name,
          industry: ex.industry,
          offer: ex.offer,
          audience: ex.audience,
          cta: ex.cta,
          tone: ex.tone,
        }).then(function () { say("Exemple « " + ex.label + " » chargé."); });
      };
    });

    Array.prototype.forEach.call(host.querySelectorAll("[data-angle]"), function (b) {
      b.onclick = function () {
        var ang = _state.angles[parseInt(b.dataset.angle, 10)];
        if (!ang) return;
        topicEl.value = ang.topic;
        topicEl.focus();
        say("Idée « " + ang.label + " » prête — clique sur Fabriquer ou Générer le script.");
      };
    });
  }

  function renderSettingsPersonality() {
    var grid = document.querySelector("#view-reglages .conn-opt-grid");
    if (!grid) return;
    var card = document.getElementById("cr-personality-settings-card");
    if (!card) {
      card = document.createElement("div");
      card.id = "cr-personality-settings-card";
      card.className = "conn-opt-plaque lg-sheen";
      grid.appendChild(card);
    }
    var p = _state.personality || { mode: "creator" };
    var isBiz = p.mode === "business";
    var isCustom = p.mode === "custom" && !!_state.activeCustom;
    var ac = _state.activeCustom;
    var label = isCustom ? ac.name : (isBiz ? "Entreprise" : "Créateur");
    var desc = isCustom
      ? (ac.mission || "Personnalité personnalisée active.")
      : (isBiz
        ? ((p.company_name || "Entreprise") + (p.industry ? " · " + p.industry : "") + (p.offer ? " — " + p.offer : ""))
        : "Mode Créateur normal : contenu libre sur n'importe quel sujet.");
    card.innerHTML =
      '<div>' +
        '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">' +
          '<div class="conn-mini-ico" style="margin-bottom:0;font-weight:800;font-size:13px;">ID</div>' +
          '<span style="font-size:12px;font-weight:700;color:var(--ok);">' + esc(label) + "</span>" +
        "</div>" +
        '<div style="font-weight:700;font-size:15px;color:var(--ink);">Personnalité de création</div>' +
        '<div style="font-size:12px;color:var(--muted);margin-top:4px;line-height:1.45;">' + esc(desc) + "</div>" +
      "</div>" +
      '<div style="margin-top:12px;padding-top:10px;border-top:1px solid var(--border);display:flex;gap:8px;flex-wrap:wrap;">' +
        '<button type="button" class="btn btn-primary btn-xs" id="cr-set-edit-pers">Gérer dans Créer</button>' +
      "</div>";

    card.querySelector("#cr-set-edit-pers").onclick = function () {
      if (typeof window.showView === "function") window.showView("creer");
    };
  }

  // ---------- Mes 5 Comptes Concurrents (S'inspirer — édition perso) ----------
  async function loadCompetitors() {
    var sec = document.getElementById("view-analyse");
    if (!sec) return;
    try {
      var r = await fetch("/api/competitors", { cache: "no-store" });
      if (!r.ok) return; // 403 en édition public -> rien injecté
      var d = await r.json();
      _state.competitors = d.competitors || [];
      renderCompetitorsPanel();
    } catch (e) {}
  }

  function renderCompetitorsPanel() {
    var sec = document.getElementById("view-analyse");
    if (!sec) return;
    var panel = document.getElementById("cr-competitors-panel");
    if (!panel) {
      panel = document.createElement("div");
      panel.id = "cr-competitors-panel";
      panel.className = "card lg-sheen cr-comp-card";
      var firstCard = sec.querySelector(".card");
      if (firstCard) sec.insertBefore(panel, firstCard);
      else sec.appendChild(panel);
    }
    var inputs = "";
    for (var i = 0; i < 5; i++) {
      var val = (_state.competitors[i] && _state.competitors[i].handle) || "";
      inputs += '<input type="text" class="input-sm cr-comp-inp" data-ci="' + i + '" value="' + esc(val) + '" placeholder="Concurrent ' + (i + 1) + ' (@compte ou lien YouTube/TikTok)">';
    }
    panel.innerHTML =
      '<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:10px;flex-wrap:wrap;">' +
        '<div>' +
          '<div style="font-weight:800;font-size:15.5px;color:var(--ink);">Mes 5 comptes concurrents</div>' +
          '<div style="font-size:12.5px;color:var(--muted);margin-top:3px;">Ajoute jusqu\'à 5 comptes à surveiller puis lance un scan pour repérer leurs vidéos qui performent le mieux et actualiser le radar.</div>' +
        '</div>' +
        '<div style="display:flex;gap:8px;flex-wrap:wrap;">' +
          '<button type="button" class="btn btn-ghost btn-sm" id="cr-comp-save">Enregistrer</button>' +
          '<button type="button" class="btn btn-coral btn-sm" id="cr-comp-scan">Scanner</button>' +
        '</div>' +
      '</div>' +
      '<div class="cr-comp-inputs">' + inputs + '</div>' +
      '<div id="cr-comp-status" style="font-size:12.5px;color:var(--muted);margin-top:10px;"></div>' +
      '<div id="cr-comp-results" class="cr-comp-results"></div>';

    function collect() {
      return Array.prototype.map.call(panel.querySelectorAll(".cr-comp-inp"), function (el) {
        return (el.value || "").trim();
      }).filter(Boolean);
    }

    panel.querySelector("#cr-comp-save").onclick = async function () {
      var list = collect();
      var r = await fetch("/api/competitors", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ competitors: list }),
      });
      var d = await r.json().catch(function () { return {}; });
      if (!r.ok || d.error) return say(d.error || "Erreur d'enregistrement.");
      _state.competitors = d.competitors || [];
      say(_state.competitors.length + " compte(s) concurrent(s) enregistré(s).");
    };

    panel.querySelector("#cr-comp-scan").onclick = async function () {
      var list = collect();
      var btn = panel.querySelector("#cr-comp-scan");
      var stEl = panel.querySelector("#cr-comp-status");
      var resEl = panel.querySelector("#cr-comp-results");
      btn.disabled = true;
      btn.textContent = "Scan en cours…";
      if (typeof window.scanInspiration === "function") {
        try { window.scanInspiration(); } catch (e) {}
      }
      if (!list.length) {
        stEl.textContent = "Radar actualisé. Ajoute jusqu'à 5 comptes ci-dessus pour scanner aussi tes concurrents.";
        btn.disabled = false;
        btn.textContent = "Scanner";
        return;
      }
      stEl.innerHTML = '<span class="pulse-dot"></span>Analyse de tes ' + list.length + " compte(s) concurrent(s) et actualisation du radar en cours…";
      try {
        var r = await fetch("/api/competitors/scan", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ competitors: list, threshold: 2.0, limit: 20 }),
        });
        var d = await r.json().catch(function () { return {}; });
        if (!r.ok || d.error) {
          stEl.textContent = d.error || "Scan impossible.";
          return;
        }
        var outs = d.outliers || [];
        var errTxt = (d.errors && d.errors.length) ? " · Erreurs : " + d.errors.join(" ; ") : "";
        stEl.textContent = outs.length + " vidéo(s) marquante(s) trouvée(s)" + errTxt;
        resEl.innerHTML = outs.map(function (o, idx) {
          return '<div class="cr-comp-item">' +
            '<div style="display:flex;justify-content:space-between;align-items:center;gap:6px;">' +
              '<span class="cr-comp-ratio">×' + esc(String(o.ratio || 2)) + ' vues</span>' +
              '<span style="font-size:11.5px;color:var(--muted);">' + esc(o.competitor || "") + " · " + fmtViews(o.views) + " vues</span>" +
            '</div>' +
            '<div style="font-weight:700;font-size:13.5px;color:var(--ink);line-height:1.35;">' + esc(o.title || "Short viral") + '</div>' +
            '<div style="display:flex;gap:6px;margin-top:auto;flex-wrap:wrap;">' +
              '<button type="button" class="btn btn-coral btn-xs cr-comp-use" data-oi="' + idx + '">Reprendre la structure</button>' +
              (o.url ? '<a class="btn btn-ghost btn-xs" href="' + esc(o.url) + '" target="_blank" rel="noopener">Voir</a>' : "") +
            '</div>' +
          '</div>';
        }).join("");

        Array.prototype.forEach.call(resEl.querySelectorAll(".cr-comp-use"), function (b) {
          b.onclick = function () {
            var item = outs[parseInt(b.dataset.oi, 10)];
            if (!item) return;
            if (typeof window.showView === "function") window.showView("creer");
            var ta = document.getElementById("main-topic");
            if (ta) {
              ta.value = item.recipe_brief || "";
              ta.focus();
            }
            say("Structure prête dans Créer.");
          };
        });
      } catch (e) {
        stEl.textContent = "Connexion impossible au serveur ClipRoll.";
      } finally {
        btn.disabled = false;
        btn.textContent = "Scanner";
      }
    };
  }

  window.ClipoaPersonality = {
    refresh: function () { return Promise.all([loadPersonality(), loadCompetitors()]); },
    getState: function () { return _state; },
    savePersonality: savePersonality,
  };

  function boot() {
    loadPersonality();
    loadCompetitors();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
