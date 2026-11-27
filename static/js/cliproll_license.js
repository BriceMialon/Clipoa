// Licence d'abonnement (version publique) : carte dans Connexions + message quand la fabrication est bloquée.
// API : /api/license/status | activate | deactivate | link. Rien ne s'affiche en édition perso (required=false).
(function () {
  "use strict";
  var state = null;
  var CSS = ".lic-card{margin:0 0 16px;padding:16px 18px;border-radius:18px;border:1px solid var(--border);background:var(--glass);display:flex;flex-direction:column;gap:10px}" +
    ".lic-head{display:flex;align-items:center;gap:10px}.lic-title{margin:0;font-size:17px;color:var(--ink)}" +
    ".lic-badge{margin-left:auto;font-size:12px;font-weight:700;padding:3px 10px;border-radius:999px;background:var(--glass-soft);color:var(--muted)}" +
    ".lic-badge.ok{background:var(--ok,#22c55e);color:#fff}.lic-badge.ko{background:var(--danger,#ef4444);color:#fff}" +
    ".lic-txt{margin:0;color:var(--ink-2);font-size:14px;line-height:1.45}.lic-row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}" +
    ".lic-input{flex:1;min-width:220px;box-sizing:border-box;padding:10px 12px;border-radius:12px;border:1px solid var(--border-hi);background:var(--glass-soft);color:var(--ink);font-size:15px;font-family:ui-monospace,monospace;text-transform:uppercase}";
  var st = document.createElement("style"); st.textContent = CSS; document.head.appendChild(st);

  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function say(msg, type) { if (window.__crToast) window.__crToast(msg, type); }
  function day(ts) { try { return new Date(ts * 1000).toLocaleDateString("fr-FR", { day: "numeric", month: "long" }); } catch (e) { return ""; } }

  function call(path, body) {
    return fetch("/api/license/" + path, {
      method: body ? "POST" : "GET", cache: "no-store",
      headers: body ? { "Content-Type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined
    }).then(function (r) { return r.json(); }).catch(function () { return { error: "ClipRoll ne répond pas." }; });
  }

  function card() {
    var c = document.getElementById("lic-card");
    if (c) return c;
    var view = document.getElementById("view-reglages");
    var head = view && view.querySelector(".page-head");
    if (!head) return null;
    c = document.createElement("div"); c.id = "lic-card"; c.className = "lic-card";
    head.insertAdjacentElement("afterend", c);
    c.addEventListener("click", onClick);
    c.addEventListener("keydown", function (e) { if (e.key === "Enter" && e.target.id === "lic-key") activate(); });
    return c;
  }

  function render() {
    var c = card();
    if (!c || !state || !state.required) { if (c) c.remove(); return; }
    var s = state.state, html;
    if (state.valid) {
      var label = s === "trialing" ? "Essai gratuit" : s === "past_due" ? "Paiement à régulariser" : "Abonnement actif";
      var plan = state.plan === "yearly" ? "annuel" : state.plan === "monthly" ? "mensuel" : "";
      html = '<div class="lic-head"><h2 class="lic-title">Licence</h2><span class="lic-badge ok">' + esc(label) + '</span></div>' +
        '<p class="lic-txt">Abonnement ' + esc(plan) + ' · clé se terminant par ' + esc(state.key_hint) +
        (state.period_end ? ' · prochaine échéance le ' + esc(day(state.period_end)) : '') + '.</p>' +
        (s === "past_due" ? '<p class="lic-txt">Le dernier paiement a échoué : mettez votre carte à jour pour garder l\'accès.</p>' : '') +
        '<div class="lic-row"><button type="button" class="btn btn-primary btn-sm" data-act="portal">Gérer l\'abonnement</button>' +
        '<button type="button" class="btn btn-ghost btn-sm" data-act="deactivate">Libérer cet ordinateur</button></div>';
    } else {
      var msg = s === "expired"
        ? "Votre abonnement n'est plus actif. Vos vidéos restent là, mais la fabrication est en pause."
        : "Collez la clé reçue après votre paiement. Essai gratuit de 3 jours en vous abonnant.";
      html = '<div class="lic-head"><h2 class="lic-title">Licence</h2><span class="lic-badge ' + (s === "expired" ? "ko" : "") + '">' +
        (s === "expired" ? "Inactive" : "Non activée") + '</span></div><p class="lic-txt">' + esc(msg) + '</p>' +
        '<div class="lic-row"><input id="lic-key" class="lic-input" placeholder="CLIPOA-XXXX-XXXX-XXXX-XXXX" autocomplete="off" spellcheck="false" aria-label="Clé de licence">' +
        '<button type="button" class="btn btn-primary btn-sm" data-act="activate">Activer</button></div>' +
        '<div class="lic-row"><button type="button" class="btn btn-ghost btn-sm" data-act="subscribe" data-plan="yearly">S\'abonner · 149 €/an</button>' +
        '<button type="button" class="btn btn-ghost btn-sm" data-act="subscribe" data-plan="monthly">19 €/mois</button>' +
        (s === "expired" ? '<button type="button" class="btn btn-ghost btn-sm" data-act="portal">Gérer l\'abonnement</button>' : '') + '</div>';
    }
    c.innerHTML = html;
  }

  function activate() {
    var inp = document.getElementById("lic-key");
    var key = inp ? inp.value.trim() : "";
    if (!key) return say("Collez votre clé de licence.", "error");
    call("activate", { key: key }).then(function (d) {
      if (d.error) return say(d.error, "error");
      state = d; render(); say("Licence activée. Bonne création !", "success");
    });
  }

  function link(kind, plan) {
    var w = window.open("about:blank", "_blank"); // ouvert tout de suite pour éviter le bloqueur de fenêtres
    call("link", { kind: kind, plan: plan }).then(function (d) {
      if (d.error || !d.url) { if (w) w.close(); return say(d.error || "Lien indisponible.", "error"); }
      if (w) { try { w.opener = null; } catch (e) {} w.location.href = d.url; } else { window.location.href = d.url; }
    });
  }

  function onClick(e) {
    var b = e.target.closest("[data-act]");
    if (!b) return;
    var act = b.getAttribute("data-act");
    if (act === "activate") activate();
    else if (act === "portal") link("portal");
    else if (act === "subscribe") link("checkout", b.getAttribute("data-plan"));
    else if (act === "deactivate") {
      if (!window.confirm("Libérer cet ordinateur ? Vous pourrez réactiver la clé ici ou sur un autre ordinateur.")) return;
      call("deactivate", {}).then(function (d) { if (!d.error) { state = d; render(); say("Cet ordinateur est libéré."); } });
    }
  }

  function refresh() { return call("status").then(function (d) { if (!d.error) { state = d; render(); } return d; }); }

  // Fabrication refusée faute de licence (HTTP 402) : on explique et on ouvre la carte Licence.
  var origFetch = window.fetch;
  window.fetch = function () {
    return origFetch.apply(this, arguments).then(function (r) {
      if (r.status === 402) {
        r.clone().json().then(function (d) {
          if (!d || !d.license_required) return;
          say(d.error || "Activez votre licence pour fabriquer des vidéos.", "error");
          if (typeof window.showView === "function") window.showView("reglages");
          refresh().then(function () { var i = document.getElementById("lic-key"); if (i) i.focus(); });
        }).catch(function () {});
      }
      return r;
    });
  };

  window.ClipRollLicense = { refresh: refresh };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", refresh); else refresh();
})();
