// Bandeau « Mettre à jour » (installation par install.sh uniquement ; muet sur une copie de développement).
(function () {
  "use strict";
  var bar = null;

  function el(tag, css, text) {
    var e = document.createElement(tag);
    if (css) e.style.cssText = css;
    if (text) e.textContent = text;
    return e;
  }

  function show(info) {
    if (bar) return;
    bar = el("div", "position:fixed;right:16px;bottom:16px;z-index:99999;max-width:340px;padding:14px 16px;border-radius:14px;" +
      "background:rgba(20,20,28,.92);color:#fff;font:14px/1.4 -apple-system,system-ui,sans-serif;box-shadow:0 8px 30px rgba(0,0,0,.35)");
    var title = el("div", "font-weight:600;margin-bottom:4px", "Nouvelle version de ClipRoll : " + info.latest);
    var notes = el("div", "opacity:.8;font-size:13px;margin-bottom:10px", info.notes || "Tu as la version " + info.current + ".");
    var msg = el("div", "font-size:13px;margin-top:8px;display:none");
    var btn = el("button", "background:#7c5cff;color:#fff;border:0;border-radius:10px;padding:8px 14px;font-weight:600;cursor:pointer", "Mettre à jour");
    var later = el("button", "background:transparent;color:#bbb;border:0;margin-left:8px;cursor:pointer", "Plus tard");
    later.onclick = function () { bar.remove(); bar = null; };
    btn.onclick = function () {
      btn.disabled = true; later.style.display = "none"; msg.style.display = "block"; msg.textContent = "Préparation…";
      fetch("/api/update/apply", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" })
        .then(function (r) { return r.json(); })
        .then(function (res) {
          if (!res.ok) { msg.textContent = res.error || "Mise à jour impossible."; btn.disabled = false; return; }
          poll(msg, btn, info.latest);
        })
        .catch(function () { msg.textContent = "Mise à jour impossible (réseau)."; btn.disabled = false; });
    };
    bar.appendChild(title); bar.appendChild(notes); bar.appendChild(btn); bar.appendChild(later); bar.appendChild(msg);
    document.body.appendChild(bar);
  }

  function poll(msg, btn, target) {
    fetch("/api/update/status", { cache: "no-store" })
      .then(function (r) { return r.json(); })
      .then(function (s) {
        if (s.current === target) { msg.textContent = "C'est fait. Rechargement…"; setTimeout(function () { location.reload(); }, 800); return; }
        var st = s.state || {};
        if (st.error) { msg.textContent = st.error; btn.disabled = false; return; }
        msg.textContent = (st.step || "Mise à jour…") + (st.progress ? " " + st.progress + " %" : "");
        setTimeout(function () { poll(msg, btn, target); }, 1000);
      })
      .catch(function () { msg.textContent = "Redémarrage de ClipRoll…"; setTimeout(function () { poll(msg, btn, target); }, 1500); });
  }

  function check() {
    fetch("/api/update/status", { cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (info) { if (info && info.enabled && info.available) show(info); })
      .catch(function () {});
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", check); else check();
})();
