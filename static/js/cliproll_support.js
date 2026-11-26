// Rapport de plantage + « Contacter le support ».
// Rien n'est envoyé sans clic sur « Envoyer » ; l'utilisateur peut voir le contenu exact avant.
(function () {
  "use strict";
  var SEEN_KEY = "clipoa_support_seen";
  var bubble = null;
  var modal = null;

  function el(tag, css, text) {
    var e = document.createElement(tag);
    if (css) e.style.cssText = css;
    if (text) e.textContent = text;
    return e;
  }

  function post(url, body) {
    return fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) })
      .then(function (r) { return r.json().catch(function () { return { ok: false, error: "Réponse invalide" }; }); });
  }

  function seen() {
    try { return JSON.parse(localStorage.getItem(SEEN_KEY) || "[]"); } catch (e) { return []; }
  }
  function markSeen(id) {
    try { var s = seen(); s.push(id); localStorage.setItem(SEEN_KEY, JSON.stringify(s.slice(-50))); } catch (e) { /* stockage indisponible */ }
  }

  function download(report) {
    var blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "rapport-clipoa.json";
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 2000);
  }

  function close() { if (modal) { modal.remove(); modal = null; } }

  function open(opts) {
    opts = opts || {};
    close();
    var isContact = !opts.incidentId;
    var card = "background:var(--bg,#16161e);color:var(--ink,#fff);border-radius:16px;padding:20px 22px;width:min(520px,92vw);" +
      "max-height:88vh;overflow:auto;box-shadow:0 20px 60px rgba(0,0,0,.45);font:14px/1.45 -apple-system,system-ui,sans-serif";
    var field = "width:100%;box-sizing:border-box;margin-top:6px;padding:10px 12px;border-radius:10px;border:1px solid rgba(127,127,127,.35);" +
      "background:rgba(127,127,127,.08);color:inherit;font:inherit";
    modal = el("div", "position:fixed;inset:0;z-index:100000;background:rgba(0,0,0,.5);display:flex;align-items:center;justify-content:center");
    modal.addEventListener("click", function (e) { if (e.target === modal) close(); });
    var box = el("div", card);
    box.setAttribute("role", "dialog");
    box.setAttribute("aria-modal", "true");

    box.appendChild(el("div", "font-size:17px;font-weight:700;margin-bottom:6px",
      isContact ? "Contacter le support" : "Envoyer le rapport d'erreur"));
    if (opts.summary) box.appendChild(el("div", "font-size:13px;color:var(--danger,#ff6b6b);margin-bottom:8px;word-break:break-word", opts.summary));
    box.appendChild(el("div", "font-size:13px;opacity:.8;margin-bottom:12px",
      isContact
        ? "Pose ta question ou décris ce qui ne va pas. On te répond par e-mail."
        : "Le rapport contient la version de ClipRoll, ton système, l'étape en erreur et les journaux récents. " +
          "Tes clés API, jetons, mots de passe et vidéos ne sont jamais envoyés."));

    var msgLabel = el("label", "display:block;font-weight:600;font-size:13px",
      isContact ? "Ton message" : "Que faisais-tu ? (facultatif)");
    var msg = el("textarea", field + ";min-height:90px;resize:vertical");
    msg.maxLength = 4000;
    msgLabel.appendChild(msg);
    box.appendChild(msgLabel);

    var mailLabel = el("label", "display:block;font-weight:600;font-size:13px;margin-top:10px",
      "Ton e-mail pour la réponse (facultatif)");
    var mail = el("input", field);
    mail.type = "email"; mail.autocomplete = "email"; mail.maxLength = 200;
    try { mail.value = localStorage.getItem("clipoa_support_email") || ""; } catch (e) { /* rien */ }
    mailLabel.appendChild(mail);
    box.appendChild(mailLabel);

    var logsRow = el("label", "display:flex;gap:8px;align-items:center;margin-top:12px;font-size:13px;cursor:pointer");
    var logs = el("input"); logs.type = "checkbox"; logs.checked = true;
    logsRow.appendChild(logs);
    logsRow.appendChild(el("span", "", "Joindre les journaux techniques nettoyés (aide beaucoup à corriger)"));
    box.appendChild(logsRow);

    var previewLink = el("button", "background:none;border:0;padding:0;margin-top:10px;color:var(--accent,#7c5cff);cursor:pointer;font:inherit;font-size:13px;text-decoration:underline",
      "Voir exactement ce qui sera envoyé");
    var pre = el("pre", "display:none;margin-top:8px;max-height:240px;overflow:auto;font-size:12px;white-space:pre-wrap;word-break:break-word;" +
      "background:rgba(127,127,127,.1);padding:10px;border-radius:10px");
    box.appendChild(previewLink); box.appendChild(pre);

    box.appendChild(el("div", "font-size:12px;opacity:.65;margin-top:10px",
      "En cliquant sur Envoyer, tu acceptes que ces informations soient transmises à l'équipe ClipRoll pour corriger le problème ou te répondre. " +
      "Elles sont supprimées automatiquement après 90 jours."));

    var status = el("div", "font-size:13px;margin-top:10px;display:none");
    var row = el("div", "display:flex;gap:8px;justify-content:flex-end;margin-top:14px;flex-wrap:wrap");
    var cancel = el("button", "background:transparent;color:inherit;border:1px solid rgba(127,127,127,.35);border-radius:10px;padding:8px 14px;cursor:pointer;font:inherit", "Annuler");
    var send = el("button", "background:var(--accent,#7c5cff);color:#fff;border:0;border-radius:10px;padding:8px 16px;font-weight:600;cursor:pointer;font:inherit", "Envoyer");
    row.appendChild(cancel); row.appendChild(send);
    box.appendChild(status); box.appendChild(row);
    modal.appendChild(box);
    document.body.appendChild(modal);
    msg.focus();

    function payload() {
      return {
        kind: isContact ? "contact" : "crash",
        incident_id: opts.incidentId || "",
        message: msg.value,
        contact_email: mail.value.trim(),
        include_logs: logs.checked,
        page: (location.hash || location.pathname || "").slice(0, 200),
      };
    }

    cancel.onclick = close;
    previewLink.onclick = function () {
      post("/api/support/preview", payload()).then(function (res) {
        pre.style.display = "block";
        pre.textContent = JSON.stringify(res.report || res, null, 2);
      });
    };
    send.onclick = function () {
      if (isContact && !msg.value.trim()) { msg.focus(); return; }
      send.disabled = true; status.style.display = "block"; status.textContent = "Envoi…";
      try { if (mail.value.trim()) localStorage.setItem("clipoa_support_email", mail.value.trim()); } catch (e) { /* rien */ }
      post("/api/support/send", payload()).then(function (res) {
        if (res.ok) {
          if (opts.incidentId) markSeen(opts.incidentId);
          status.textContent = "Merci, c'est envoyé. Numéro du rapport : " + (res.report_id || "—");
          send.style.display = "none"; cancel.textContent = "Fermer";
          if (bubble && opts.incidentId) { bubble.remove(); bubble = null; }
          return;
        }
        send.disabled = false;
        status.textContent = (res.error || "Envoi impossible.") + " ";
        if (res.report) {
          var dl = el("button", "background:none;border:0;padding:0;color:var(--accent,#7c5cff);cursor:pointer;font:inherit;text-decoration:underline",
            "Télécharger le rapport pour l'envoyer à la main");
          dl.onclick = function () { download(res.report); };
          status.appendChild(dl);
        }
      }).catch(function () { send.disabled = false; status.textContent = "Envoi impossible (ClipRoll ne répond pas)."; });
    };
  }

  // Plantage hors fabrication (serveur, tâche de fond) : petite bulle discrète
  function showBubble(inc) {
    if (bubble) return;
    bubble = el("div", "position:fixed;left:16px;bottom:16px;z-index:99998;max-width:330px;padding:12px 14px;border-radius:14px;" +
      "background:rgba(20,20,28,.94);color:#fff;font:13px/1.4 -apple-system,system-ui,sans-serif;box-shadow:0 8px 30px rgba(0,0,0,.35)");
    bubble.appendChild(el("div", "font-weight:600;margin-bottom:6px", "ClipRoll a rencontré un problème"));
    bubble.appendChild(el("div", "opacity:.75;margin-bottom:10px;word-break:break-word", (inc.message || "").slice(0, 140)));
    var go = el("button", "background:#7c5cff;color:#fff;border:0;border-radius:10px;padding:7px 12px;font-weight:600;cursor:pointer", "Envoyer un rapport");
    var no = el("button", "background:transparent;color:#bbb;border:0;margin-left:8px;cursor:pointer", "Ignorer");
    go.onclick = function () { open({ incidentId: inc.id, summary: inc.message }); };
    no.onclick = function () {
      markSeen(inc.id); post("/api/support/dismiss", { incident_id: inc.id });
      bubble.remove(); bubble = null;
    };
    bubble.appendChild(go); bubble.appendChild(no);
    document.body.appendChild(bubble);
  }

  function check() {
    fetch("/api/support/incidents", { cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (res) {
        if (!res || !res.incidents) return;
        var s = seen();
        // les échecs de fabrication ont déjà leur bouton sur la carte de la tâche
        var todo = res.incidents.filter(function (i) { return i.source !== "job" && s.indexOf(i.id) < 0; });
        if (todo.length) showBubble(todo[todo.length - 1]);
      })
      .catch(function () {});
  }

  window.ClipoaSupport = { open: open, openContact: function () { open({}); } };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", check); else check();
  setInterval(check, 60000);
})();
