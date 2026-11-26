# ClipRoll — Sécurité, Anti-DDoS & Checklist avant sortie publique

## 1. Protections intégrées dans le code

### Application locale (`app.py`, `core/security.py`, `config.py`, `core/scraper.py`)
- **Écoute locale stricte par défaut (`127.0.0.1`)** : ClipRoll n'est plus exposé sur tout le Wi-Fi public (café, hôtel, fac).
  - Pour autoriser l'accès depuis son téléphone sur son Wi-Fi privé : lancer avec `CLIPOA_ALLOW_LAN=1`. Un jeton aléatoire est automatiquement généré (`http://<IP>:8080/?token=...`) et stocké en cookie `HttpOnly; SameSite=Lax`.
- **Anti-SSRF & Anti-injection d'arguments** :
  - Validation stricte de toutes les URLs publiques (`/api/scan`, `/api/clone`, `/api/cut`, `/api/analyze-short`, `yt-dlp`) : blocage de `file://`, `localhost`, IP privées (`10.x`, `192.168.x`, `169.254.169.254`), résolution DNS privée et flags commençant par `-`.
  - Séparateur `--` systématique avant les URLs dans `yt-dlp`, allowlist stricte des navigateurs pour `--cookies-from-browser`, et plafond `--max-filesize 750M` (configurable via `CLIPOA_MAX_DOWNLOAD_SIZE`).
- **Confinement des fichiers locaux** :
  - `/api/make` (`background_video`) et `/api/cut` (`source`) refusent tout fichier hors de `storage/` ou d'extension non-média (empêche la lecture arbitraire de fichiers système).
- **Relais OAuth HTTPS obligatoire** : `save_relay_config` bloque tout relais distant en `http://` en clair.
- **Garde-fous CPU / RAM / Disque** :
  - `JobConcurrencyGuard` : limite à **2 tâches lourdes simultanées** (FFmpeg / Whisper / IA) et **6 en file max** (`CLIPOA_MAX_CONCURRENT_JOBS`, `CLIPOA_MAX_ACTIVE_JOBS`) pour éviter de faire planter le PC.
  - Timeouts sur **tous** les appels FFmpeg (`30s` à `600s`) et `yt-dlp`.
  - Nettoyage automatique au démarrage des fichiers temporaires (`storage/downloads`, `storage/audio`) de plus de 7 jours (`CLIPOA_TEMP_TTL_DAYS`), sans jamais toucher `storage/renders`.
  - Nouveaux endpoints : `GET /api/system/health` et `POST /api/system/cleanup`.
- **Rate limiting borné en mémoire** : 3 niveaux (polling 240/min, API 60/min, actions lourdes IA/rendu 15/min) avec en-tête `Retry-After` et purge automatique anti-fuite RAM.
- **Permissions strictes (`0600`)** : appliquées automatiquement au démarrage sur `social_accounts.json`, `oauth_apps.json`, `settings.json`, `claude_usage.json`, `gemini_usage.json`, `publish_queue.json`, `jobs_history.json`.
- **Portabilité multi-utilisateurs** : suppression du chemin codé en dur `/Users/brice/.local/bin/claude` dans `config.py`.

### Relais OAuth Cloudflare Worker (`oauth_relay_worker.js`)
- **Rate limiting anti-DDoS intégré** par IP (`CF-Connecting-IP`) :
  - `/oauth/*/refresh` : 30 req/min
  - `/oauth/*/start` & `/callback` : 20 req/min
  - `/oauth/status`, `/terms`, `/privacy` : 60 req/min
- **Paramètre `state` signé HMAC-SHA256 + expiration 10 min** (anti-falsification & anti-replay).
- **Plafond de payload (8 Ko)** sur `/refresh`, timeouts réseau 10 s sur Google/TikTok/Meta, validation stricte `isAllowedReturnTo`, méthodes HTTP vérifiées (`405`), en-têtes de sécurité complets (`HSTS`, `CSP` avec `form-action` verrouillé, `X-Frame-Options: DENY`).

---

## 2. Actions Cloudflare à activer avant la sortie publique (gratuit)

1. **Déployer le `oauth_relay_worker.js` durci** sur ton Worker `clipoa-oauth` après comparaison avec tes routes légales.
2. **Ajouter le secret `STATE_SECRET`** dans Cloudflare → `clipoa-oauth` → *Paramètres → Variables et secrets* (générer une chaîne aléatoire de 48+ caractères).
3. **Activer la protection DDoS / Rate Limiting au niveau Edge Cloudflare** (si tu branches un domaine perso devant le Worker) :
   - *Security → WAF → Rate limiting rules* : limiter `POST /oauth/*/refresh` à 30 req/min par IP (action : *Block*).
   - *Workers & Pages → Usage Model* : rester sur le plan gratuit (100 000 req/jour) ou définir un plafond d'alerte de facturation.
4. **Ne jamais pousser `storage/*.json` sur GitHub** (vérifier `.gitignore`) : ces fichiers contiennent tes tokens locaux.
