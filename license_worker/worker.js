// Serveur de licence ClipRoll (Cloudflare Worker + D1).
// - POST /checkout            {plan}            -> URL Stripe Checkout (abonnement, essai 3 j, carte demandée)
// - GET  /success?session_id=                    -> page qui affiche la clé de licence
// - POST /portal              {key}             -> URL du portail client Stripe (carte, factures, résiliation)
// - POST /stripe/webhook                         -> événements Stripe (signature vérifiée + envoi email clé)
// - POST /license/activate    {key, device, device_name}
// - POST /license/refresh     {key, device}     -> nouveau jeton, ou {revoked:true}
// - POST /license/deactivate  {key, device}     -> libère un appareil
// Jeton : base64url(JSON) + "." + base64url(signature Ed25519), vérifié hors ligne par l'app (core/license.py).

const OK_STATUSES = ["active", "trialing", "past_due"];
const KEY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"; // sans 0/O/1/I
const enc = new TextEncoder();
const DEFAULT_ALLOWED_ORIGINS = [
  "https://cliproll.app",
  "https://www.cliproll.app",
  "http://localhost:8080",
  "http://127.0.0.1:8080",
];

// ---------- In-Isolate Bounded Rate Limiter ----------
const _rateBuckets = new Map();
const MAX_RATE_BUCKETS = 2000;
const _ISOLATE_SALT = crypto.randomUUID();

async function hashIp(request) {
  const raw =
    request.headers.get("CF-Connecting-IP") ||
    (request.headers.get("X-Forwarded-For") || "").split(",")[0].trim() ||
    "unknown";
  const digest = await crypto.subtle.digest("SHA-256", enc.encode(`${_ISOLATE_SALT}:${raw}`));
  return b64url(digest).slice(0, 22);
}

function allowRate(key, maxHits, windowMs) {
  const now = Date.now();
  const cutoff = now - windowMs;
  if (_rateBuckets.size > MAX_RATE_BUCKETS) {
    for (const [k, hits] of _rateBuckets) {
      if (!hits.length || hits[hits.length - 1] < cutoff) _rateBuckets.delete(k);
      if (_rateBuckets.size <= MAX_RATE_BUCKETS * 0.8) break;
    }
    if (_rateBuckets.size > MAX_RATE_BUCKETS) {
      const oldest = _rateBuckets.keys().next().value;
      if (oldest) _rateBuckets.delete(oldest);
    }
  }
  let hits = _rateBuckets.get(key);
  if (!hits) {
    hits = [];
    _rateBuckets.set(key, hits);
  }
  while (hits.length && hits[0] < cutoff) hits.shift();
  if (hits.length >= maxHits) {
    return { allowed: false, retryAfter: Math.max(1, Math.ceil((windowMs - (now - hits[0])) / 1000)) };
  }
  hits.push(now);
  return { allowed: true, retryAfter: 0 };
}

// ---------- CORS & Security Helpers ----------
function allowedOrigins(env) {
  const raw = String((env && env.ALLOWED_ORIGINS) || "").trim();
  if (!raw) return DEFAULT_ALLOWED_ORIGINS;
  return raw.split(",").map((s) => s.trim()).filter(Boolean);
}

function corsHeaders(request, env) {
  const origin = request ? (request.headers.get("Origin") || "") : "";
  if (!origin) return {};
  if (!allowedOrigins(env).includes(origin)) return {};
  return {
    "access-control-allow-origin": origin,
    "access-control-allow-methods": "GET, POST, OPTIONS",
    "access-control-allow-headers": "Content-Type, X-Clipoa-License",
    "access-control-max-age": "600",
    vary: "Origin",
  };
}

function json(data, status = 200, extraHeaders = {}) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
      "x-content-type-options": "nosniff",
      ...extraHeaders,
    },
  });
}

function escapeHtml(s) {
  return String(s || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function b64url(bytes) {
  let s = "";
  for (const b of new Uint8Array(bytes)) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function newKey() {
  const r = crypto.getRandomValues(new Uint8Array(16));
  const chars = [...r].map((b) => KEY_ALPHABET[b % 32]).join("");
  return "CLIPOA-" + chars.match(/.{4}/g).join("-");
}

function normKey(k) {
  const v = String(k || "").replace(/\s+/g, "").toUpperCase();
  return /^CLIPOA(-[A-Z0-9]{4}){3,4}$/.test(v) ? v : "";
}

function cleanDevice(d) {
  const v = String(d || "");
  return /^[a-f0-9]{16,64}$/.test(v) ? v : "";
}

async function sha256hex(s) {
  const h = await crypto.subtle.digest("SHA-256", enc.encode(s));
  return [...new Uint8Array(h)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

// ---------------------------------------------------------------- Stripe
async function stripe(env, method, path, params) {
  const body = params ? new URLSearchParams(params).toString() : undefined;
  const url = "https://api.stripe.com/v1/" + path + (method === "GET" && body ? "?" + body : "");
  const r = await fetch(url, {
    method,
    headers: {
      authorization: "Bearer " + env.STRIPE_SECRET_KEY,
      "content-type": "application/x-www-form-urlencoded",
    },
    body: method === "GET" ? undefined : body,
  });
  let data = {};
  try {
    data = await r.json();
  } catch {
    data = {};
  }
  if (!r.ok) throw new Error((data.error && data.error.message) || "Stripe HTTP " + r.status);
  return data;
}

function assertTestMode(env) {
  // Sécurité : tant que Brice n'a pas validé le passage en live, seules les clés de test sont acceptées.
  if (!String(env.STRIPE_SECRET_KEY || "").startsWith("sk_test_") && env.ALLOW_LIVE !== "yes") {
    throw new Error("Clé Stripe live refusée (ALLOW_LIVE non activé).");
  }
}

async function verifyStripeSignature(env, payload, header) {
  if (!env.STRIPE_WEBHOOK_SECRET) return false;
  const parts = Object.fromEntries(
    String(header || "").split(",").map((p) => p.split("=").map((x) => x.trim()))
  );
  const sigs = String(header || "").split(",").filter((p) => p.trim().startsWith("v1=")).map((p) => p.trim().slice(3));
  const t = Number(parts.t || 0);
  if (!t || !sigs.length || Math.abs(Date.now() / 1000 - t) > 300) return false;
  const key = await crypto.subtle.importKey("raw", enc.encode(env.STRIPE_WEBHOOK_SECRET), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const mac = await crypto.subtle.sign("HMAC", key, enc.encode(t + "." + payload));
  const expected = [...new Uint8Array(mac)].map((b) => b.toString(16).padStart(2, "0")).join("");
  return sigs.some((s) => s.length === expected.length && timingSafeEqual(s, expected));
}

function timingSafeEqual(a, b) {
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

function planOf(env, sub) {
  const price = sub && sub.items && sub.items.data && sub.items.data[0] && sub.items.data[0].price;
  if (!price) return null;
  if (price.id === env.PRICE_YEARLY) return "yearly";
  if (price.id === env.PRICE_MONTHLY) return "monthly";
  return price.recurring && price.recurring.interval === "year" ? "yearly" : "monthly";
}

function periodEnd(sub) {
  // Selon la version d'API, la fin de période est sur l'abonnement ou sur l'item.
  return sub.current_period_end || (sub.items && sub.items.data && sub.items.data[0] && sub.items.data[0].current_period_end) || null;
}

async function sendLicenseEmail(env, email, key, maxDevices) {
  // Envoi automatique via Resend si RESEND_API_KEY est configuré ; sans impact sinon.
  if (!env.RESEND_API_KEY || !email) return false;
  const from = env.MAIL_FROM || "ClipRoll <licence@cliproll.app>";
  const safeKey = escapeHtml(key);
  const html = `
    <div style="font-family:system-ui,-apple-system,sans-serif;max-width:520px;margin:24px auto;color:#111;line-height:1.55;">
      <h1 style="font-size:22px;margin:0 0 12px;">Bienvenue sur ClipRoll</h1>
      <p>Merci pour votre abonnement ! Voici votre clé de licence personnelle :</p>
      <p style="font-size:20px;font-weight:700;letter-spacing:0.06em;background:#f4f4f6;padding:12px 16px;border-radius:10px;display:inline-block;">${safeKey}</p>
      <p><strong>Comment l'activer :</strong> ouvrez ClipRoll → <em>Connexions</em> → <em>Licence ClipRoll</em>, collez cette clé et cliquez sur <em>Activer</em>.</p>
      <p style="color:#555;font-size:13px;">Valable sur ${Number(maxDevices || 2)} ordinateurs. Conservez cet email en lieu sûr.</p>
    </div>`;
  try {
    const res = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: {
        authorization: "Bearer " + env.RESEND_API_KEY,
        "content-type": "application/json",
      },
      body: JSON.stringify({
        from,
        to: [email],
        subject: "Votre clé de licence ClipRoll",
        html,
        text: `Bienvenue sur ClipRoll !\n\nVotre clé de licence : ${key}\n\nCollez-la dans ClipRoll (Connexions -> Licence ClipRoll). Valable sur ${Number(maxDevices || 2)} ordinateurs.`,
      }),
    });
    if (!res.ok) {
      console.error(JSON.stringify({ event: "license_email_failed", status: res.status }));
      return false;
    }
    return true;
  } catch (err) {
    console.error(JSON.stringify({ event: "license_email_error", error: String(err && err.message || err) }));
    return false;
  }
}

async function upsertFromSubscription(env, sub, email) {
  const customer = typeof sub.customer === "string" ? sub.customer : sub.customer.id;
  const subId = sub.id || null;
  const subStatus = sub.status || "incomplete";
  const plan = planOf(env, sub);
  const pEnd = periodEnd(sub);
  const now = Math.floor(Date.now() / 1000);
  const candidateKey = newKey();

  // Atomique : empêche les races UNIQUE(customer_id) entre webhook et /success,
  // et empêche un webhook tardif d'un ancien abonnement résilié d'écraser un nouvel abonnement actif.
  const existingBefore = await env.DB.prepare(
    "SELECT key, subscription_id, status FROM licenses WHERE customer_id = ?"
  ).bind(customer).first();

  if (
    existingBefore &&
    existingBefore.subscription_id &&
    subId &&
    existingBefore.subscription_id !== subId &&
    OK_STATUSES.includes(existingBefore.status) &&
    !OK_STATUSES.includes(subStatus)
  ) {
    // Ancien abonnement résilié/expiré arrivant en retard : on conserve l'abonnement actif le plus récent.
    return { key: existingBefore.key, created: false };
  }

  await env.DB.prepare(
    `INSERT INTO licenses (key, customer_id, subscription_id, email, plan, status, period_end, created_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?)
     ON CONFLICT(customer_id) DO UPDATE SET
       subscription_id = excluded.subscription_id,
       status = excluded.status,
       plan = COALESCE(excluded.plan, licenses.plan),
       period_end = COALESCE(excluded.period_end, licenses.period_end),
       email = COALESCE(excluded.email, licenses.email)`
  ).bind(candidateKey, customer, subId, email || null, plan, subStatus, pEnd, now).run();

  const row = await env.DB.prepare("SELECT key FROM licenses WHERE customer_id = ?").bind(customer).first();
  const actualKey = row ? row.key : candidateKey;
  return { key: actualKey, created: !existingBefore && actualKey === candidateKey };
}

async function handleWebhook(request, env) {
  assertTestMode(env);
  const payload = await request.text();
  if (!(await verifyStripeSignature(env, payload, request.headers.get("stripe-signature")))) {
    return json({ error: "signature" }, 400);
  }
  const event = JSON.parse(payload);
  // Idempotence atomique via INSERT OR IGNORE
  const ins = await env.DB.prepare(
    "INSERT OR IGNORE INTO stripe_events (id, at) VALUES (?, ?)"
  ).bind(event.id, Math.floor(Date.now() / 1000)).run();
  if (!ins.meta || ins.meta.changes === 0) {
    return json({ received: true, duplicate: true });
  }

  const obj = event.data.object;
  if (event.type === "checkout.session.completed" && obj.mode === "subscription" && obj.subscription) {
    const sub = await stripe(env, "GET", "subscriptions/" + obj.subscription);
    const email = (obj.customer_details && obj.customer_details.email) || null;
    const { key, created } = await upsertFromSubscription(env, sub, email);
    if (created && email) {
      await sendLicenseEmail(env, email, key, env.MAX_DEVICES || 2);
    }
  } else if (event.type.startsWith("customer.subscription.")) {
    await upsertFromSubscription(env, obj, null);
  }
  return json({ received: true });
}

// ---------------------------------------------------------------- Jetons
async function signToken(env, lic, device) {
  const now = Math.floor(Date.now() / 1000);
  const days = Number(env.TOKEN_DAYS || 7);
  // Plafond : jamais au-delà de period_end + 3 j ; en past_due, jeton court de 3 j max.
  let exp = now + (lic.status === "past_due" ? Math.min(days, 3) : days) * 86400;
  if (lic.period_end) {
    const cap = Number(lic.period_end) + 3 * 86400;
    exp = Math.min(exp, cap);
  }
  if (exp <= now) {
    return null;
  }
  const payload = {
    key: (await sha256hex(lic.key)).slice(0, 16),
    dev: device,
    plan: lic.plan,
    status: lic.status,
    period_end: lic.period_end,
    iat: now,
    exp,
  };
  const body = enc.encode(JSON.stringify(payload));
  const der = Uint8Array.from(atob(env.LICENSE_SIGNING_KEY), (c) => c.charCodeAt(0));
  const sk = await crypto.subtle.importKey("pkcs8", der, { name: "Ed25519" }, false, ["sign"]);
  const sig = await crypto.subtle.sign({ name: "Ed25519" }, sk, body);
  return b64url(body) + "." + b64url(sig);
}

async function getLicense(env, key) {
  return key ? env.DB.prepare("SELECT * FROM licenses WHERE key = ?").bind(key).first() : null;
}

async function handleActivate(env, body, cors) {
  const key = normKey(body.key);
  const device = cleanDevice(body.device);
  if (!key || !device) return json({ error: "Clé ou appareil invalide." }, 400, cors);
  const lic = await getLicense(env, key);
  if (!lic) return json({ error: "Clé inconnue." }, 404, cors);
  if (!OK_STATUSES.includes(lic.status)) return json({ error: "Abonnement inactif. Réabonnez-vous depuis le site." }, 403, cors);

  const now = Math.floor(Date.now() / 1000);
  const maxDevices = Number(env.MAX_DEVICES || 2);
  const devName = String(body.device_name || "").slice(0, 60);

  // Mise à jour si déjà enregistré, sinon insertion atomique conditionnée à COUNT(*) < MAX_DEVICES
  const upd = await env.DB.prepare(
    "UPDATE devices SET last_seen = ?, name = ? WHERE key = ? AND device = ?"
  ).bind(now, devName, key, device).run();
  if (!upd.meta || upd.meta.changes === 0) {
    const ins = await env.DB.prepare(
      `INSERT OR IGNORE INTO devices (key, device, name, last_seen)
       SELECT ?, ?, ?, ? WHERE (SELECT COUNT(*) FROM devices WHERE key = ?) < ?`
    ).bind(key, device, devName, now, key, maxDevices).run();
    if (!ins.meta || ins.meta.changes === 0) {
      return json({ error: "Nombre maximal d'appareils atteint. Libérez un appareil depuis ClipRoll sur l'autre ordinateur." }, 409, cors);
    }
  }
  const token = await signToken(env, lic, device);
  if (!token) return json({ error: "Période d'abonnement expirée. Vérifiez votre paiement Stripe." }, 403, cors);
  return json({ token }, 200, cors);
}

async function handleRefresh(env, body, cors) {
  const key = normKey(body.key);
  const device = cleanDevice(body.device);
  const lic = await getLicense(env, key);
  const known = lic && (await env.DB.prepare("SELECT device FROM devices WHERE key = ? AND device = ?").bind(key, device).first());
  if (!lic || !known || !OK_STATUSES.includes(lic.status)) return json({ revoked: true }, 200, cors);
  const token = await signToken(env, lic, device);
  if (!token) return json({ revoked: true }, 200, cors);
  await env.DB.prepare("UPDATE devices SET last_seen = ? WHERE key = ? AND device = ?").bind(Math.floor(Date.now() / 1000), key, device).run();
  return json({ token }, 200, cors);
}

async function handleDeactivate(env, body, cors) {
  const key = normKey(body.key);
  const device = cleanDevice(body.device);
  if (key && device) await env.DB.prepare("DELETE FROM devices WHERE key = ? AND device = ?").bind(key, device).run();
  return json({ ok: true }, 200, cors);
}

// ---------------------------------------------------------------- Pages
function page(title, html) {
  return new Response(
    `<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${escapeHtml(title)}</title>
<style>body{font-family:system-ui,sans-serif;max-width:560px;margin:60px auto;padding:0 16px;color:#111}code{font-size:1.3em;background:#f2f2f2;padding:8px 12px;border-radius:8px;display:inline-block;user-select:all}</style>${html}`,
    {
      headers: {
        "content-type": "text/html; charset=utf-8",
        "cache-control": "no-store",
        "content-security-policy": "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'",
        "x-frame-options": "DENY",
        "x-content-type-options": "nosniff",
        "referrer-policy": "no-referrer",
        "strict-transport-security": "max-age=31536000; includeSubDomains",
      },
    }
  );
}

async function handleSuccess(env, url) {
  assertTestMode(env);
  const sid = String(url.searchParams.get("session_id") || "");
  if (!/^cs_[A-Za-z0-9_]+$/.test(sid)) return page("ClipRoll", "<p>Lien invalide.</p>");
  const session = await stripe(env, "GET", "checkout/sessions/" + sid);
  if (session.status !== "complete" || !session.subscription) return page("ClipRoll", "<p>Paiement non finalisé.</p>");
  // Le webhook peut arriver après la redirection : on crée la licence ici aussi (idempotent).
  const sub = await stripe(env, "GET", "subscriptions/" + session.subscription);
  const email = (session.customer_details && session.customer_details.email) || null;
  const { key, created } = await upsertFromSubscription(env, sub, email);
  if (created && email) {
    await sendLicenseEmail(env, email, key, env.MAX_DEVICES || 2);
  }
  const safeKey = escapeHtml(key);
  return page("Votre licence ClipRoll", `<h1>Merci !</h1><p>Votre clé de licence :</p><p><code>${safeKey}</code></p>
<p>Collez-la dans ClipRoll (Connexions → Licence ClipRoll). Elle fonctionne sur ${Number(env.MAX_DEVICES || 2)} ordinateurs.</p>`);
}

async function handleCheckout(env, body, cors) {
  assertTestMode(env);
  const plan = body.plan === "yearly" ? "yearly" : "monthly";
  const price = plan === "yearly" ? env.PRICE_YEARLY : env.PRICE_MONTHLY;
  const base = env.PUBLIC_URL;
  const session = await stripe(env, "POST", "checkout/sessions", {
    mode: "subscription",
    "line_items[0][price]": price,
    "line_items[0][quantity]": "1",
    "subscription_data[trial_period_days]": String(Number(env.TRIAL_DAYS || 3)),
    payment_method_collection: "always", // essai 3 j avec carte demandée (choix de Brice, 26/11/2026)
    allow_promotion_codes: "true",
    billing_address_collection: "auto",
    success_url: base + "/success?session_id={CHECKOUT_SESSION_ID}",
    cancel_url: base + "/",
  });
  return json({ url: session.url }, 200, cors);
}

async function handlePortal(env, body, cors) {
  assertTestMode(env);
  const lic = await getLicense(env, normKey(body.key));
  if (!lic) return json({ error: "Clé inconnue." }, 404, cors);
  const s = await stripe(env, "POST", "billing_portal/sessions", { customer: lic.customer_id, return_url: env.PUBLIC_URL + "/" });
  return json({ url: s.url }, 200, cors);
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const cors = corsHeaders(request, env);
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: cors });
    }
    try {
      if (request.method === "GET" && url.pathname === "/") {
        return json({ service: "clipoa-license", ok: true }, 200, cors);
      }
      if (request.method === "GET" && url.pathname === "/success") {
        return await handleSuccess(env, url);
      }
      if (request.method !== "POST") return json({ error: "not found" }, 404, cors);
      if (url.pathname === "/stripe/webhook") return await handleWebhook(request, env);

      // Rate-limit par IP hachée (anti-spam Stripe & brute-force clés)
      const ipHash = await hashIp(request);
      const isCheckout = url.pathname === "/checkout" || url.pathname === "/portal";
      const rl = allowRate(`${isCheckout ? "pay" : "lic"}:${ipHash}`, isCheckout ? 10 : 30, 60_000);
      if (!rl.allowed) {
        return json({ error: "Trop de requêtes. Réessayez dans une minute." }, 429, {
          ...cors,
          "retry-after": String(rl.retryAfter),
        });
      }

      const body = await request.json().catch(() => ({}));
      if (url.pathname === "/checkout") return await handleCheckout(env, body, cors);
      if (url.pathname === "/portal") return await handlePortal(env, body, cors);
      if (url.pathname === "/license/activate") return await handleActivate(env, body, cors);
      if (url.pathname === "/license/refresh") return await handleRefresh(env, body, cors);
      if (url.pathname === "/license/deactivate") return await handleDeactivate(env, body, cors);
      return json({ error: "not found" }, 404, cors);
    } catch (e) {
      console.error(JSON.stringify({ event: "license_worker_error", path: url.pathname, error: String((e && e.message) || e) }));
      return json({ error: "Erreur interne du serveur de licence." }, 500, cors);
    }
  },
};
