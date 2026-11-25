# Clipoa — État d'Avancement & Passation pour Claude

**Date de mise à jour :** 24 novembre 2026  
**Dossier local sur le Mac :** `/Users/brice/.gemini/antigravity/scratch/shortcrew_clone`  
**Serveur local :** `http://localhost:8080` (`./venv/bin/python app.py`)  
**Tests automatisés :** `./venv/bin/python -m unittest discover -s tests -v` (**21/21 OK**)

---

## 1. Ce qui est terminé et 100 % fonctionnel dans le code

### A. Studio, Création IA, Montage & Sécurité
- Routage unifié `(Claude / Gemini) × (Fond animé / B-roll / Blender 3D / Mode Nuit)`.
- Boost Rétention FFmpeg (`core/video_composer.py`), synthèse vocale Edge TTS / Gemini / ElevenLabs, transcription Whisper thread-safe.
- Design **Apple Liquid Glass** (`static/css/liquid-glass.css`) avec 4 piliers (`Studio`, `Bibliothèque`, `Diffusion`, `Tendances`), palette rapide `⌘K` et dock mobile.
- Durcissement sécurité dans `app.py` (anti-scraping, rate limiting IP, CSRF same-origin, anti path-traversal, anti-SSRF `/api/thumb`, écritures JSON atomiques `0o600`).

### B. Publication Multi-Réseaux 1-Clic & Programmation (`core/social_publisher.py`, `app.py`, `templates/index.html`)
- **4 boutons OAuth 2.0 1-clic** directement en haut de **Diffusion → Publier & Calendrier** (`YouTube`, `Instagram`, `Facebook`, `TikTok`) :
  - `/oauth/youtube/start`, `/oauth/instagram/start`, `/oauth/facebook/start`, `/oauth/tiktok/start`
  - Protection CSRF `state`/`nonce` + redirection retour directe vers `Diffusion` (`/?view=auto&connected=...`).
- **Import direct de Short (.mp4 / .mov / .webm)** dans Diffusion (`POST /api/videos/upload` avec optimisation FFmpeg `-movflags +faststart` H.264/AAC).
- **Publication immédiate (asynchrone avec suivi en direct)** OU **Programmation différée** (scheduler en arrière-plan + renouvellement automatique des tokens expirés avant publication).
- **Les 4 APIs officielles corrigées et prêtes :**
  1. **YouTube Shorts** : YouTube Data API v3 (resumable upload + tag `#Shorts` auto + refresh token auto).
  2. **Instagram Reels** : Instagram Graph API via **Resumable Binary Upload** (`rupload.facebook.com/ig-api-upload`) → envoie directement le `.mp4` local sans ngrok ni bucket S3 + scan de toutes les Pages Facebook pour trouver automatiquement le compte Instagram Pro lié.
  3. **Facebook Reels** : Facebook Graph API 3 phases `/{page_id}/video_reels` (vrai format Reels) + échange automatique en **Long-Lived Token** (tokens de Page permanents).
  4. **TikTok** : Content Posting API v2 (`FILE_UPLOAD` + `creator_info/query` + `status/fetch` + refresh token 365j + fallback transparent `SELF_ONLY` tant que l'app n'est pas auditée).

### C. Relais OAuth 1-Clic SaaS déjà déployé sur Cloudflare Workers
- **URL en ligne (HTTPS actif) :** `https://clipoa-oauth.clipoa-studio.workers.dev`
- **Status endpoint :** `https://clipoa-oauth.clipoa-studio.workers.dev/oauth/status`
- **Code source :** `oauth_relay_worker.js`
- **Cloudflare Account ID :** `9259000c2824289dc9ef561f30dd60f5` (compte `brice.mialon01800@gmail.com`)
- **Retour sécurisé :** formulaire `POST` auto-soumis vers `http://localhost:8080/oauth/<provider>/relay-done` (aucun token dans l'URL) + endpoints `/oauth/youtube/refresh` et `/oauth/tiktok/refresh`.

---

## 2. Ce qu'il reste à faire (Mission exacte pour Claude)

> **Objectif :** Finaliser la configuration des 3 consoles développeurs (Google Cloud, Meta, TikTok) afin que cliquer sur **Se connecter** sur YouTube, Instagram, Facebook et TikTok dans `http://localhost:8080` ouvre directement les vrais portails de connexion natifs (sans que Brice n'ait rien à faire manuellement).

### Étape 1 — Google Cloud Console (YouTube)
- Le Client ID OAuth est **déjà enregistré localement** dans `storage/oauth_apps.json` :
  - `client_id` : `261175281110-ne6h7tj7uv66bcb75dem0e0sp90hqk0q.apps.googleusercontent.com`
- À vérifier / ajouter sur `https://console.cloud.google.com/apis/credentials` (projet `261175281110`) :
  1. Vérifier que **YouTube Data API v3** est activée (`https://console.cloud.google.com/apis/library/youtube.googleapis.com`).
  2. Dans **Audience / OAuth consent screen**, vérifier que `brice.mialon01800@gmail.com` est bien dans **Test users**.
  3. Dans le client OAuth Web `261175281110-...`, ajouter dans **URI de redirection autorisés** :
     - `http://localhost:8080/oauth/youtube/callback`
     - `https://clipoa-oauth.clipoa-studio.workers.dev/oauth/youtube/callback`
  4. *(Bonus SaaS)* Ajouter les secrets `YT_CLIENT_ID` et `YT_CLIENT_SECRET` sur le Worker Cloudflare `clipoa-oauth`.

### Étape 2 — Meta for Developers (Instagram Reels + Facebook Reels)
- Sur `https://developers.facebook.com/apps/` :
  1. Créer une application type **Business** nommée `Clipoa` (email `brice.mialon01800@gmail.com`).
  2. Ajouter **Facebook Login for Business** → dans *URI de redirection OAuth valides*, ajouter :
     - `http://localhost:8080/oauth/meta/callback`
     - `https://clipoa-oauth.clipoa-studio.workers.dev/oauth/meta/callback`
  3. Récupérer `App ID` + `App Secret` dans *Paramètres → Général*.
  4. Les enregistrer dans Clipoa (`POST http://localhost:8080/api/social/oauth-app` avec `provider="meta"`, ou dans `storage/oauth_apps.json`) **et** comme secrets `META_APP_ID` / `META_APP_SECRET` sur le Worker Cloudflare `clipoa-oauth`.

### Étape 3 — TikTok for Developers (TikTok)
- Sur `https://developers.tiktok.com/apps/` :
  1. Créer / connecter une app Web nommée `Clipoa`.
  2. Activer **Login Kit** (Redirect URI : `https://clipoa-oauth.clipoa-studio.workers.dev/oauth/tiktok/callback`) + **Content Posting API** (`Direct Post`, scopes `user.info.basic`, `video.publish`, `video.upload`).
  3. Récupérer `Client Key` + `Client Secret`.
  4. Les enregistrer comme secrets `TT_CLIENT_KEY` / `TT_CLIENT_SECRET` sur le Worker Cloudflare `clipoa-oauth` (et/ou localement dans Clipoa).

### Étape 4 — Vérification finale
- Aller sur `http://localhost:8080` → onglet **Diffusion** → vérifier que les 4 boutons **Se connecter** (YouTube, Instagram, Facebook, TikTok) redirigent directement vers les portails officiels respectifs, ramènent sur Clipoa en état `✓ Connecté`, et permettent la publication directe + programmation.
