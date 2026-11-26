// Serveur de licence Clipoa (Cloudflare Worker + D1).
// - POST /checkout            {plan}            -> URL Stripe Checkout (abonnement, essai 7 j, carte demandée)
// - GET  /success?session_id=                    -> page qui affiche la clé de licence
// - POST /portal              {key}             -> URL du portail client Stripe (carte, factures, résiliation)
// - POST /stripe/webhook                         -> événements Stripe (signature vérifiée)
// - POST /license/activate    {key, device, device_name}
// - POST /license/refresh     {key, device}     -> nouveau jeton, ou {revoked:true}
// - POST /license/deactivate  {key, device}     -> libère un appareil
// Jeton : base64url(JSON) + "." + base64url(signature Ed25519), vérifié hors ligne par l'app (core/license.py).

const OK_STATUSES = ["active", "trialing", "past_due"];
const KEY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"; // sans 0/O/1/I
const enc = new TextEncoder();

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
  });
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
  const data = await r.json();
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

async function upsertFromSubscription(env, sub, email) {
  const customer = typeof sub.customer === "string" ? sub.customer : sub.customer.id;
  const existing = await env.DB.prepare("SELECT key FROM licenses WHERE customer_id = ?").bind(customer).first();
  if (existing) {
    await env.DB.prepare(
      "UPDATE licenses SET subscription_id = ?, status = ?, plan = ?, period_end = ?, email = COALESCE(?, email) WHERE customer_id = ?"
    ).bind(sub.id, sub.status, planOf(env, sub), periodEnd(sub), email || null, customer).run();
    return existing.key;
  }
  const key = newKey();
  await env.DB.prepare(
    "INSERT INTO licenses (key, customer_id, subscription_id, email, plan, status, period_end, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
  ).bind(key, customer, sub.id, email || null, planOf(env, sub), sub.status, periodEnd(sub), Math.floor(Date.now() / 1000)).run();
  return key;
}

async function handleWebhook(request, env) {
  const payload = await request.text();
  if (!(await verifyStripeSignature(env, payload, request.headers.get("stripe-signature")))) {
    return json({ error: "signature" }, 400);
  }
  const event = JSON.parse(payload);
  const seen = await env.DB.prepare("SELECT id FROM stripe_events WHERE id = ?").bind(event.id).first();
  if (seen) return json({ received: true, duplicate: true });

  const obj = event.data.object;
  if (event.type === "checkout.session.completed" && obj.mode === "subscription" && obj.subscription) {
    const sub = await stripe(env, "GET", "subscriptions/" + obj.subscription);
    await upsertFromSubscription(env, sub, obj.customer_details && obj.customer_details.email);
  } else if (event.type.startsWith("customer.subscription.")) {
    await upsertFromSubscription(env, obj, null);
  }
  await env.DB.prepare("INSERT INTO stripe_events (id, at) VALUES (?, ?)").bind(event.id, Math.floor(Date.now() / 1000)).run();
  return json({ received: true });
}

// ---------------------------------------------------------------- Jetons
async function signToken(env, lic, device) {
  const now = Math.floor(Date.now() / 1000);
  const days = Number(env.TOKEN_DAYS || 7);
  // Le jeton n'est jamais valable au-delà de la fin de période + 3 jours (sauf relances past_due).
  let exp = now + days * 86400;
  if (lic.period_end && lic.status !== "past_due") exp = Math.min(exp, lic.period_end + 3 * 86400);
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

async function handleActivate(env, body) {
  const key = normKey(body.key);
  const device = cleanDevice(body.device);
  if (!key || !device) return json({ error: "Clé ou appareil invalide." }, 400);
  const lic = await getLicense(env, key);
  if (!lic) return json({ error: "Clé inconnue." }, 404);
  if (!OK_STATUSES.includes(lic.status)) return json({ error: "Abonnement inactif. Réabonnez-vous depuis le site." }, 403);

  const known = await env.DB.prepare("SELECT device FROM devices WHERE key = ? AND device = ?").bind(key, device).first();
  if (!known) {
    const { n } = await env.DB.prepare("SELECT COUNT(*) AS n FROM devices WHERE key = ?").bind(key).first();
    if (n >= Number(env.MAX_DEVICES || 2)) {
      return json({ error: "Nombre maximal d'appareils atteint. Libérez un appareil depuis Clipoa sur l'autre ordinateur." }, 409);
    }
  }
  await env.DB.prepare(
    "INSERT INTO devices (key, device, name, last_seen) VALUES (?, ?, ?, ?) ON CONFLICT(key, device) DO UPDATE SET last_seen = excluded.last_seen, name = excluded.name"
  ).bind(key, device, String(body.device_name || "").slice(0, 60), Math.floor(Date.now() / 1000)).run();
  return json({ token: await signToken(env, lic, device) });
}

async function handleRefresh(env, body) {
  const key = normKey(body.key);
  const device = cleanDevice(body.device);
  const lic = await getLicense(env, key);
  const known = lic && (await env.DB.prepare("SELECT device FROM devices WHERE key = ? AND device = ?").bind(key, device).first());
  if (!lic || !known || !OK_STATUSES.includes(lic.status)) return json({ revoked: true });
  await env.DB.prepare("UPDATE devices SET last_seen = ? WHERE key = ? AND device = ?").bind(Math.floor(Date.now() / 1000), key, device).run();
  return json({ token: await signToken(env, lic, device) });
}

async function handleDeactivate(env, body) {
  const key = normKey(body.key);
  const device = cleanDevice(body.device);
  if (key && device) await env.DB.prepare("DELETE FROM devices WHERE key = ? AND device = ?").bind(key, device).run();
  return json({ ok: true });
}

// ---------------------------------------------------------------- Pages
function page(title, html) {
  return new Response(
    `<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${title}</title>
<style>body{font-family:system-ui,sans-serif;max-width:560px;margin:60px auto;padding:0 16px;color:#111}code{font-size:1.3em;background:#f2f2f2;padding:8px 12px;border-radius:8px;display:inline-block;user-select:all}</style>${html}`,
    { headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" } }
  );
}

async function handleSuccess(env, url) {
  const sid = String(url.searchParams.get("session_id") || "");
  if (!/^cs_[A-Za-z0-9_]+$/.test(sid)) return page("Clipoa", "<p>Lien invalide.</p>");
  const session = await stripe(env, "GET", "checkout/sessions/" + sid);
  if (session.status !== "complete" || !session.subscription) return page("Clipoa", "<p>Paiement non finalisé.</p>");
  // Le webhook peut arriver après la redirection : on crée la licence ici aussi (idempotent).
  const sub = await stripe(env, "GET", "subscriptions/" + session.subscription);
  const key = await upsertFromSubscription(env, sub, session.customer_details && session.customer_details.email);
  return page("Votre licence Clipoa", `<h1>Merci !</h1><p>Votre clé de licence :</p><p><code>${key}</code></p>
<p>Collez-la dans Clipoa (Réglages, Licence). Elle fonctionne sur ${Number(env.MAX_DEVICES || 2)} ordinateurs.</p>`);
}

async function handleCheckout(env, body) {
  const plan = body.plan === "yearly" ? "yearly" : "monthly";
  const price = plan === "yearly" ? env.PRICE_YEARLY : env.PRICE_MONTHLY;
  const base = env.PUBLIC_URL;
  const session = await stripe(env, "POST", "checkout/sessions", {
    mode: "subscription",
    "line_items[0][price]": price,
    "line_items[0][quantity]": "1",
    "subscription_data[trial_period_days]": String(Number(env.TRIAL_DAYS || 7)),
    payment_method_collection: "always", // essai 7 j avec carte demandée (choix de Brice, 26/11/2026)
    allow_promotion_codes: "true",
    billing_address_collection: "auto",
    success_url: base + "/success?session_id={CHECKOUT_SESSION_ID}",
    cancel_url: base + "/",
  });
  return json({ url: session.url });
}

async function handlePortal(env, body) {
  const lic = await getLicense(env, normKey(body.key));
  if (!lic) return json({ error: "Clé inconnue." }, 404);
  const s = await stripe(env, "POST", "billing_portal/sessions", { customer: lic.customer_id, return_url: env.PUBLIC_URL + "/" });
  return json({ url: s.url });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    try {
      assertTestMode(env);
      if (request.method === "GET" && url.pathname === "/") return json({ service: "clipoa-license", ok: true });
      if (request.method === "GET" && url.pathname === "/success") return handleSuccess(env, url);
      if (request.method !== "POST") return json({ error: "not found" }, 404);
      if (url.pathname === "/stripe/webhook") return handleWebhook(request, env);
      const body = await request.json().catch(() => ({}));
      if (url.pathname === "/checkout") return handleCheckout(env, body);
      if (url.pathname === "/portal") return handlePortal(env, body);
      if (url.pathname === "/license/activate") return handleActivate(env, body);
      if (url.pathname === "/license/refresh") return handleRefresh(env, body);
      if (url.pathname === "/license/deactivate") return handleDeactivate(env, body);
      return json({ error: "not found" }, 404);
    } catch (e) {
      return json({ error: String((e && e.message) || e) }, 500);
    }
  },
};
