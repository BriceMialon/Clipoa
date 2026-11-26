/**
 * ClipRoll 1-Click OAuth Relay (Cloudflare Worker — Hardened Production Edition)
 *
 * Permet à tous les utilisateurs de ClipRoll de cliquer sur :
 *   - « Se connecter à YouTube »
 *   - « Se connecter à Instagram »
 *   - « Se connecter à Facebook »
 *   - « Se connecter à TikTok »
 * d'être redirigés vers le portail officiel, puis renvoyés automatiquement dans ClipRoll
 * avec rafraîchissement automatique des tokens (programmation différée 24h/24).
 *
 * Protections intégrées :
 *   - Rate limiting anti-DDoS par IP et par route (avec Retry-After et mémoire bornée)
 *   - Paramètre OAuth `state` signé HMAC-SHA256 avec expiration (TTL 10 min)
 *   - Validation stricte de `return_to` (anti Open-Redirect / Path Traversal)
 *   - Plafond de taille de payload JSON (8 Ko) sur les endpoints /refresh
 *   - Timeout réseau 10 s sur tous les appels upstream (Google / TikTok / Meta)
 *   - En-têtes de sécurité complets (CSP avec form-action verrouillé, HSTS, nosniff, DENY)
 *
 * Secrets Cloudflare Worker à configurer (1 seule fois par l'éditeur de ClipRoll) :
 *   - YT_CLIENT_ID, YT_CLIENT_SECRET
 *   - TT_CLIENT_KEY, TT_CLIENT_SECRET
 *   - META_APP_ID, META_APP_SECRET
 *   - Recommandé : STATE_SECRET (chaîne aléatoire 32+ caractères pour signer le state OAuth)
 *   - Optionnel : ALLOWED_RETURN_ORIGIN (ex: "https://app.clipoa.com")
 */

const GRAPH_VERSION = "v21.0";
const STATE_TTL_MS = 10 * 60 * 1000; // 10 minutes
const MAX_REFRESH_BODY_BYTES = 8 * 1024; // 8 KB
const UPSTREAM_TIMEOUT_MS = 10_000; // 10 s

// ---------- In-Isolate Bounded Sliding-Window Rate Limiter (Zero Raw IP Storage) ----------
const _rateBuckets = new Map();
const MAX_RATE_BUCKETS = 2000;
const _ISOLATE_IP_SALT = crypto.randomUUID();

async function hashClientIp(request) {
  const rawIp =
    request.headers.get("CF-Connecting-IP") ||
    (request.headers.get("X-Forwarded-For") || "").split(",")[0].trim() ||
    "unknown";
  const digest = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(`${_ISOLATE_IP_SALT}:${rawIp}`)
  );
  return toBase64Url(new Uint8Array(digest)).slice(0, 22);
}

function checkRateLimit(key, maxHits, windowMs) {
  const now = Date.now();
  const cutoff = now - windowMs;

  if (_rateBuckets.size > MAX_RATE_BUCKETS) {
    for (const [k, hits] of _rateBuckets) {
      if (!hits.length || hits[hits.length - 1] < cutoff) {
        _rateBuckets.delete(k);
      }
      if (_rateBuckets.size <= MAX_RATE_BUCKETS * 0.8) break;
    }
    if (_rateBuckets.size > MAX_RATE_BUCKETS) {
      const oldestKey = _rateBuckets.keys().next().value;
      if (oldestKey) _rateBuckets.delete(oldestKey);
    }
  }

  let hits = _rateBuckets.get(key);
  if (!hits) {
    hits = [];
    _rateBuckets.set(key, hits);
  }
  while (hits.length && hits[0] < cutoff) hits.shift();
  if (hits.length >= maxHits) {
    const retryAfter = Math.max(1, Math.ceil((windowMs - (now - hits[0])) / 1000));
    return { allowed: false, retryAfter };
  }
  hits.push(now);
  return { allowed: true, retryAfter: 0 };
}

function getClientIp(request) {
  return (
    request.headers.get("CF-Connecting-IP") ||
    (request.headers.get("X-Forwarded-For") || "").split(",")[0].trim() ||
    "unknown"
  );
}

// ---------- Security Headers & Helpers ----------

function baseSecurityHeaders(extra = {}) {
  return {
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "X-Robots-Tag": "noindex, nofollow, noarchive",
    ...extra,
  };
}

function escapeHtml(str) {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function isAllowedReturnTo(rawUrl, allowedOriginEnv) {
  if (!rawUrl || String(rawUrl).length > 512) return false;
  try {
    const u = new URL(rawUrl);
    if (u.username || u.password) return false;
    if (!u.pathname.startsWith("/oauth/") || u.pathname.includes("..") || u.pathname.includes("//")) {
      return false;
    }
    if (
      u.protocol === "http:" &&
      (u.hostname === "localhost" || u.hostname === "127.0.0.1")
    ) {
      if (u.port) {
        const portNum = Number(u.port);
        if (!Number.isInteger(portNum) || portNum < 1024 || portNum > 65535) return false;
      }
      return true;
    }
    if (u.protocol === "https:" && allowedOriginEnv) {
      const allowed = allowedOriginEnv
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      if (allowed.includes(u.origin)) return true;
    }
    return false;
  } catch {
    return false;
  }
}

// ---------- HMAC-SHA256 Signed OAuth State (Anti-Tamper & Anti-Replay) ----------

function toBase64Url(bytes) {
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function fromBase64Url(str) {
  const b64 = str.replace(/-/g, "+").replace(/_/g, "/");
  const pad = b64.length % 4 === 0 ? "" : "=".repeat(4 - (b64.length % 4));
  const bin = atob(b64 + pad);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return bytes;
}

async function getStateSigningKey(env) {
  const rawSecret =
    env.STATE_SECRET ||
    env.YT_CLIENT_SECRET ||
    env.TT_CLIENT_SECRET ||
    env.META_APP_SECRET ||
    "";
  if (!rawSecret) return null;
  const enc = new TextEncoder();
  return crypto.subtle.importKey(
    "raw",
    enc.encode(`clipoa-state-v1:${rawSecret}`),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign", "verify"]
  );
}

async function encodeSignedState(obj, env) {
  const payload = { ...obj, iat: Date.now() };
  const payloadBytes = new TextEncoder().encode(JSON.stringify(payload));
  const payloadB64 = toBase64Url(payloadBytes);
  const key = await getStateSigningKey(env);
  if (!key) return payloadB64;
  const sigBuf = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(payloadB64));
  return `${payloadB64}.${toBase64Url(new Uint8Array(sigBuf))}`;
}

async function decodeAndVerifyState(raw, env) {
  if (!raw || typeof raw !== "string" || raw.length > 2048) return null;
  const parts = raw.split(".");
  const key = await getStateSigningKey(env);

  let payloadB64 = parts[0];
  if (key) {
    if (parts.length !== 2) return null;
    try {
      const sigBytes = fromBase64Url(parts[1]);
      const valid = await crypto.subtle.verify(
        "HMAC",
        key,
        sigBytes,
        new TextEncoder().encode(payloadB64)
      );
      if (!valid) return null;
    } catch {
      return null;
    }
  }

  try {
    const parsed = JSON.parse(new TextDecoder().decode(fromBase64Url(payloadB64)));
    if (!parsed || typeof parsed !== "object") return null;
    if (parsed.iat && Date.now() - Number(parsed.iat) > STATE_TTL_MS) {
      return null; // Expired state
    }
    return parsed;
  } catch {
    return null;
  }
}

async function fetchWithTimeout(url, options = {}) {
  return fetch(url, {
    ...options,
    signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
  });
}

async function readBoundedJson(request) {
  const contentLength = Number(request.headers.get("Content-Length") || 0);
  if (contentLength > MAX_REFRESH_BODY_BYTES) {
    return { error: "payload_too_large", status: 413 };
  }
  const text = await request.text();
  if (text.length > MAX_REFRESH_BODY_BYTES) {
    return { error: "payload_too_large", status: 413 };
  }
  try {
    const parsed = JSON.parse(text);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return { error: "invalid_json", status: 400 };
    }
    return { data: parsed };
  } catch {
    return { error: "invalid_json", status: 400 };
  }
}

function buildAutoPostPage(returnTo, fields) {
  let formOrigin = "'self'";
  try {
    formOrigin = new URL(returnTo).origin;
  } catch {}

  const inputs = Object.entries(fields)
    .filter(([, v]) => v !== undefined && v !== null && v !== "")
    .map(
      ([k, v]) =>
        `<input type="hidden" name="${escapeHtml(k)}" value="${escapeHtml(v)}">`
    )
    .join("\n      ");

  const html = `<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="referrer" content="no-referrer">
  <title>Connexion ClipRoll réussie…</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background:#0E0E11; color:#F4F4F6; display:flex; align-items:center; justify-content:center; height:100vh; margin:0; }
    .box { text-align:center; padding:28px 32px; border-radius:18px; background:#16161B; border:1px solid #26262E; max-width:380px; }
    button { margin-top:14px; padding:10px 18px; border-radius:10px; border:0; background:#E11D48; color:#FFFFFF; font-weight:600; cursor:pointer; }
  </style>
</head>
<body>
  <div class="box">
    <div style="font-size:16px; font-weight:600;">Connexion validée</div>
    <div style="font-size:13px; opacity:0.72; margin-top:6px;">Retour automatique vers ClipRoll…</div>
    <form id="f" method="POST" action="${escapeHtml(returnTo)}">
      ${inputs}
      <noscript><button type="submit">Continuer vers ClipRoll</button></noscript>
    </form>
  </div>
  <script>document.getElementById('f').submit();</script>
</body>
</html>`;

  return new Response(html, {
    status: 200,
    headers: baseSecurityHeaders({
      "Content-Type": "text/html; charset=utf-8",
      "Cache-Control": "no-store",
      "Content-Security-Policy": `default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; form-action ${formOrigin}; base-uri 'none'; frame-ancestors 'none'`,
    }),
  });
}

function jsonResponse(data, status = 200, extraHeaders = {}) {
  return new Response(JSON.stringify(data), {
    status,
    headers: baseSecurityHeaders({
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
      ...extraHeaders,
    }),
  });
}

function legalPage(kind) {
  const pages = {
    terms: {
      title: "ClipRoll — Conditions d'utilisation",
      body: `<p>ClipRoll est un outil personnel de création et de publication de vidéos courtes. En connectant un compte YouTube, Instagram, Facebook ou TikTok, vous autorisez ClipRoll à publier les vidéos que vous choisissez sur ce compte, uniquement à votre demande ou à l'heure que vous programmez.</p>
<p>Vous restez responsable du contenu publié et du respect des règles de chaque plateforme. Vous pouvez retirer l'accès à tout moment depuis les paramètres de sécurité de la plateforme concernée.</p>
<p>Le service est fourni tel quel, sans garantie.</p>`,
    },
    privacy: {
      title: "ClipRoll — Politique de confidentialité",
      body: `<p>ClipRoll demande uniquement les autorisations nécessaires pour publier vos vidéos et lire les informations de base de votre profil (identifiant, nom affiché).</p>
<p>Les jetons d'accès sont transmis à l'application ClipRoll installée sur votre ordinateur et y sont stockés localement. Ce relais ne conserve ni jetons ni données personnelles et ne les partage avec aucun tiers.</p>
<p>Pour supprimer vos données, déconnectez le compte dans ClipRoll et révoquez l'accès dans les paramètres de la plateforme.</p>`,
    },
  };
  const p = pages[kind];
  const html = `<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${p.title}</title><style>body{font:16px/1.6 system-ui,sans-serif;max-width:720px;margin:40px auto;padding:0 20px;color:#222}</style></head><body><h1>${p.title}</h1>${p.body}<p><small>Dernière mise à jour : 24 novembre 2026</small></p></body></html>`;
  return new Response(html, {
    headers: baseSecurityHeaders({
      "Content-Type": "text/html; charset=utf-8",
      "Cache-Control": "public, max-age=3600",
      "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'",
    }),
  });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const origin = url.origin;
    const ipHash = await hashClientIp(request);
    const method = request.method.toUpperCase();

    // Global route-tiered anti-DDoS rate limiting (keyed by salted IP hash — zero raw IP in RAM/logs)
    if (url.pathname.endsWith("/refresh")) {
      const rl = checkRateLimit(`refresh:${ipHash}`, 30, 60_000);
      if (!rl.allowed) {
        return jsonResponse(
          { ok: false, error: "rate_limited", retry_after: rl.retryAfter },
          429,
          { "Retry-After": String(rl.retryAfter) }
        );
      }
    } else if (url.pathname.startsWith("/oauth/")) {
      const rl = checkRateLimit(`oauth:${ipHash}`, 20, 60_000);
      if (!rl.allowed) {
        return jsonResponse(
          { ok: false, error: "rate_limited", retry_after: rl.retryAfter },
          429,
          { "Retry-After": String(rl.retryAfter) }
        );
      }
    } else {
      const rl = checkRateLimit(`pub:${ipHash}`, 60, 60_000);
      if (!rl.allowed) {
        return jsonResponse(
          { ok: false, error: "rate_limited", retry_after: rl.retryAfter },
          429,
          { "Retry-After": String(rl.retryAfter) }
        );
      }
    }

    // 0. Pages légales (exigées par TikTok / Meta / Google)
    if (url.pathname === "/terms" || url.pathname === "/privacy") {
      if (method !== "GET" && method !== "HEAD") {
        return jsonResponse({ ok: false, error: "method_not_allowed" }, 405);
      }
      return legalPage(url.pathname === "/terms" ? "terms" : "privacy");
    }

    // 1. Health & Configured Providers Status
    if (url.pathname === "/" || url.pathname === "/oauth/status") {
      if (method !== "GET" && method !== "HEAD") {
        return jsonResponse({ ok: false, error: "method_not_allowed" }, 405);
      }
      return jsonResponse({
        ok: true,
        service: "ClipRoll 1-Click OAuth Relay",
        hardened: true,
        callback_examples: {
          youtube: `${origin}/oauth/youtube/callback`,
          tiktok: `${origin}/oauth/tiktok/callback`,
          meta: `${origin}/oauth/meta/callback`,
        },
        providers: {
          youtube: Boolean(env.YT_CLIENT_ID && env.YT_CLIENT_SECRET),
          tiktok: Boolean(env.TT_CLIENT_KEY && env.TT_CLIENT_SECRET),
          meta: Boolean(env.META_APP_ID && env.META_APP_SECRET),
        },
      });
    }

    // 2. Token Refresh Endpoints (called server-to-server by ClipRoll Scheduler)
    if (url.pathname === "/oauth/youtube/refresh") {
      if (method !== "POST") return jsonResponse({ ok: false, error: "method_not_allowed" }, 405);
      if (!env.YT_CLIENT_ID || !env.YT_CLIENT_SECRET) {
        return jsonResponse({ ok: false, error: "youtube_relay_not_configured" }, 503);
      }
      const body = await readBoundedJson(request);
      if (body.error) return jsonResponse({ ok: false, error: body.error }, body.status);
      const rt = typeof body.data.refresh_token === "string" ? body.data.refresh_token.trim() : "";
      if (rt.length < 10 || rt.length > 4096) {
        return jsonResponse({ ok: false, error: "invalid_refresh_token" }, 400);
      }
      try {
        const tokRes = await fetchWithTimeout("https://oauth2.googleapis.com/token", {
          method: "POST",
          headers: { "Content-Type": "application/x-www-form-urlencoded" },
          body: new URLSearchParams({
            client_id: env.YT_CLIENT_ID,
            client_secret: env.YT_CLIENT_SECRET,
            refresh_token: rt,
            grant_type: "refresh_token",
          }),
        });
        const tok = await tokRes.json();
        if (!tokRes.ok || !tok.access_token) {
          return jsonResponse({ ok: false, error: tok.error_description || tok.error || "refresh_failed" }, 400);
        }
        return jsonResponse({
          ok: true,
          access_token: tok.access_token,
          expires_in: tok.expires_in || 3600,
        });
      } catch {
        return jsonResponse({ ok: false, error: "upstream_timeout" }, 504);
      }
    }

    if (url.pathname === "/oauth/tiktok/refresh") {
      if (method !== "POST") return jsonResponse({ ok: false, error: "method_not_allowed" }, 405);
      if (!env.TT_CLIENT_KEY || !env.TT_CLIENT_SECRET) {
        return jsonResponse({ ok: false, error: "tiktok_relay_not_configured" }, 503);
      }
      const body = await readBoundedJson(request);
      if (body.error) return jsonResponse({ ok: false, error: body.error }, body.status);
      const rt = typeof body.data.refresh_token === "string" ? body.data.refresh_token.trim() : "";
      if (rt.length < 10 || rt.length > 4096) {
        return jsonResponse({ ok: false, error: "invalid_refresh_token" }, 400);
      }
      try {
        const tokRes = await fetchWithTimeout("https://open.tiktokapis.com/v2/oauth/token/", {
          method: "POST",
          headers: { "Content-Type": "application/x-www-form-urlencoded" },
          body: new URLSearchParams({
            client_key: env.TT_CLIENT_KEY,
            client_secret: env.TT_CLIENT_SECRET,
            grant_type: "refresh_token",
            refresh_token: rt,
          }),
        });
        const tok = await tokRes.json();
        if (!tokRes.ok || !tok.access_token) {
          return jsonResponse({ ok: false, error: tok.error_description || tok.error || "refresh_failed" }, 400);
        }
        return jsonResponse({
          ok: true,
          access_token: tok.access_token,
          refresh_token: tok.refresh_token || rt,
          expires_in: tok.expires_in || 86400,
          open_id: tok.open_id || "",
        });
      } catch {
        return jsonResponse({ ok: false, error: "upstream_timeout" }, 504);
      }
    }

    // 3. OAuth Start Redirect
    const startMatch = url.pathname.match(/^\/oauth\/(youtube|tiktok|meta)\/start$/);
    if (startMatch) {
      if (method !== "GET") return jsonResponse({ ok: false, error: "method_not_allowed" }, 405);
      const provider = startMatch[1];
      const defaultReturn = `http://localhost:8080/oauth/${provider}/relay-done`;
      const rawReturn = url.searchParams.get("return_to") || defaultReturn;
      const returnTo = isAllowedReturnTo(rawReturn, env.ALLOWED_RETURN_ORIGIN)
        ? rawReturn
        : defaultReturn;
      const nonce = (url.searchParams.get("nonce") || crypto.randomUUID()).slice(0, 128);
      const target = (url.searchParams.get("target") || provider).slice(0, 32);
      const state = await encodeSignedState({ returnTo, nonce, target }, env);
      const redirectUri = `${origin}/oauth/${provider}/callback`;

      console.log(JSON.stringify({ event: "oauth_start", provider, target }));

      if (provider === "youtube") {
        if (!env.YT_CLIENT_ID || !env.YT_CLIENT_SECRET) {
          return buildAutoPostPage(returnTo, { error: "relais_youtube_non_configure", nonce, target });
        }
        const p = new URLSearchParams({
          client_id: env.YT_CLIENT_ID,
          redirect_uri: redirectUri,
          response_type: "code",
          scope: "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly",
          access_type: "offline",
          prompt: "consent select_account",
          include_granted_scopes: "true",
          state,
        });
        return Response.redirect(`https://accounts.google.com/o/oauth2/v2/auth?${p.toString()}`, 302);
      }

      if (provider === "tiktok") {
        if (!env.TT_CLIENT_KEY || !env.TT_CLIENT_SECRET) {
          return buildAutoPostPage(returnTo, { error: "relais_tiktok_non_configure", nonce, target });
        }
        const p = new URLSearchParams({
          client_key: env.TT_CLIENT_KEY,
          redirect_uri: redirectUri,
          response_type: "code",
          scope: "user.info.basic,video.publish,video.upload",
          state,
        });
        return Response.redirect(`https://www.tiktok.com/v2/auth/authorize/?${p.toString()}`, 302);
      }

      if (provider === "meta") {
        if (!env.META_APP_ID || !env.META_APP_SECRET) {
          return buildAutoPostPage(returnTo, { error: "relais_meta_non_configure", nonce, target });
        }
        const p = new URLSearchParams({
          client_id: env.META_APP_ID,
          redirect_uri: redirectUri,
          response_type: "code",
          scope: "pages_show_list,pages_read_engagement,pages_manage_posts,instagram_basic,instagram_content_publish,business_management",
          state,
        });
        return Response.redirect(`https://www.facebook.com/${GRAPH_VERSION}/dialog/oauth?${p.toString()}`, 302);
      }
    }

    // 4. OAuth Callback Exchange
    const cbMatch = url.pathname.match(/^\/oauth\/(youtube|tiktok|meta)\/callback$/);
    if (cbMatch) {
      if (method !== "GET") return jsonResponse({ ok: false, error: "method_not_allowed" }, 405);
      const provider = cbMatch[1];
      const code = url.searchParams.get("code");
      const err = url.searchParams.get("error_description") || url.searchParams.get("error");
      const defaultReturn = `http://localhost:8080/oauth/${provider}/relay-done`;

      const parsedState = await decodeAndVerifyState(url.searchParams.get("state") || "", env);
      if (!parsedState) {
        return buildAutoPostPage(defaultReturn, { error: "state_invalide_ou_expire", target: provider });
      }

      const returnTo =
        parsedState.returnTo && isAllowedReturnTo(parsedState.returnTo, env.ALLOWED_RETURN_ORIGIN)
          ? parsedState.returnTo
          : defaultReturn;
      const nonce = parsedState.nonce ? String(parsedState.nonce).slice(0, 128) : "";
      const target = parsedState.target ? String(parsedState.target).slice(0, 32) : provider;

      if (err || !code) {
        return buildAutoPostPage(returnTo, { error: err || "code_manquant", nonce, target });
      }
      const redirectUri = `${origin}/oauth/${provider}/callback`;

      try {
        if (provider === "youtube") {
          const tokRes = await fetchWithTimeout("https://oauth2.googleapis.com/token", {
            method: "POST",
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body: new URLSearchParams({
              code,
              client_id: env.YT_CLIENT_ID,
              client_secret: env.YT_CLIENT_SECRET,
              redirect_uri: redirectUri,
              grant_type: "authorization_code",
            }),
          });
          const tok = await tokRes.json();
          if (!tokRes.ok || !tok.access_token) {
            return buildAutoPostPage(returnTo, {
              error: tok.error_description || tok.error || "token_youtube_refuse",
              nonce,
              target,
            });
          }
          let channelName = "Chaîne YouTube";
          let channelId = "";
          try {
            const chRes = await fetchWithTimeout(
              "https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true",
              { headers: { Authorization: `Bearer ${tok.access_token}` } }
            );
            const chData = await chRes.json();
            if (chRes.ok && chData.items && chData.items.length > 0) {
              channelName = chData.items[0].snippet?.title || channelName;
              channelId = chData.items[0].id || "";
            }
          } catch {}

          console.log(JSON.stringify({ event: "oauth_callback_ok", provider: "youtube" }));
          return buildAutoPostPage(returnTo, {
            access_token: tok.access_token,
            refresh_token: tok.refresh_token || "",
            expires_in: String(tok.expires_in || 3600),
            name: channelName,
            channel_id: channelId,
            nonce,
            target,
          });
        }

        if (provider === "tiktok") {
          const tokRes = await fetchWithTimeout("https://open.tiktokapis.com/v2/oauth/token/", {
            method: "POST",
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body: new URLSearchParams({
              client_key: env.TT_CLIENT_KEY,
              client_secret: env.TT_CLIENT_SECRET,
              code,
              grant_type: "authorization_code",
              redirect_uri: redirectUri,
            }),
          });
          const tok = await tokRes.json();
          if (!tokRes.ok || !tok.access_token) {
            return buildAutoPostPage(returnTo, {
              error: tok.error_description || tok.error || "token_tiktok_refuse",
              nonce,
              target,
            });
          }
          let username = "Compte TikTok";
          try {
            const uRes = await fetchWithTimeout(
              "https://open.tiktokapis.com/v2/user/info/?fields=open_id,display_name,username",
              { headers: { Authorization: `Bearer ${tok.access_token}` } }
            );
            const uJson = await uRes.json();
            const userObj = uJson?.data?.user || {};
            if (userObj.username) username = `@${userObj.username}`;
            else if (userObj.display_name) username = userObj.display_name;
          } catch {}

          console.log(JSON.stringify({ event: "oauth_callback_ok", provider: "tiktok" }));
          return buildAutoPostPage(returnTo, {
            access_token: tok.access_token,
            refresh_token: tok.refresh_token || "",
            expires_in: String(tok.expires_in || 86400),
            open_id: tok.open_id || "",
            name: username,
            nonce,
            target,
          });
        }

        if (provider === "meta") {
          const shortUrl =
            `https://graph.facebook.com/${GRAPH_VERSION}/oauth/access_token?` +
            new URLSearchParams({
              client_id: env.META_APP_ID,
              client_secret: env.META_APP_SECRET,
              redirect_uri: redirectUri,
              code,
            }).toString();
          const shortRes = await fetchWithTimeout(shortUrl);
          const shortTok = await shortRes.json();
          if (!shortRes.ok || !shortTok.access_token) {
            return buildAutoPostPage(returnTo, {
              error: shortTok.error?.message || "token_meta_refuse",
              nonce,
              target,
            });
          }

          let userToken = shortTok.access_token;
          try {
            const longUrl =
              `https://graph.facebook.com/${GRAPH_VERSION}/oauth/access_token?` +
              new URLSearchParams({
                grant_type: "fb_exchange_token",
                client_id: env.META_APP_ID,
                client_secret: env.META_APP_SECRET,
                fb_exchange_token: shortTok.access_token,
              }).toString();
            const longRes = await fetchWithTimeout(longUrl);
            const longTok = await longRes.json();
            if (longRes.ok && longTok.access_token) {
              userToken = longTok.access_token;
            }
          } catch {}

          let pages = [];
          try {
            const pagesUrl =
              `https://graph.facebook.com/${GRAPH_VERSION}/me/accounts?` +
              new URLSearchParams({
                fields: "id,name,access_token,instagram_business_account{id,username,name}",
                access_token: userToken,
              }).toString();
            const pagesRes = await fetchWithTimeout(pagesUrl);
            const pagesJson = await pagesRes.json();
            if (pagesRes.ok && Array.isArray(pagesJson.data)) {
              pages = pagesJson.data;
            }
          } catch {}

          console.log(JSON.stringify({ event: "oauth_callback_ok", provider: "meta", pages_count: pages.length }));
          return buildAutoPostPage(returnTo, {
            access_token: userToken,
            pages_json: JSON.stringify(pages),
            nonce,
            target,
          });
        }
      } catch {
        console.error(JSON.stringify({ event: "oauth_callback_exception", provider }));
        return buildAutoPostPage(returnTo, { error: "erreur_interne_relais", nonce, target });
      }
    }

    return jsonResponse({ ok: false, error: "not_found" }, 404);
  },
};
