# Clipoa — Passation de Claude vers Antigravity (24 novembre 2026, 16 h 25)

Ce document résume tout ce que Claude a fait le 24/11/2026 entre 15 h et 16 h 25, l'état exact de chaque brique, et ce qu'il reste à faire.
Il complète `AVANCEMENT_ET_PASSATION_CLAUDE.md` (état précédent, toujours valable pour le reste du projet).

Dossier projet : `/Users/brice/.gemini/antigravity/scratch/shortcrew_clone`
Serveur local : `http://localhost:8080` (relancé par Claude avec `./venv/bin/python app.py`, log dans `storage/server.log`)
Tests : `./venv/bin/python -m unittest discover -s tests` → **28/28 OK** (21 anciens + 7 nouveaux)

---

## 1. Ce qui a été fait

### A. YouTube — fonctionne
- Google Cloud, projet `graphic-nucleus-412511` (numéro 261175281110), client OAuth Web « Client Web 1 » (`261175281110-ne6h7tj7uv66bcb75dem0e0sp90hqk0q...`).
- YouTube Data API v3 **activée** (elle ne l'était pas).
- Adresse de retour autorisée : **uniquement** `http://localhost:8080/oauth/youtube/callback`.
  L'adresse du Worker a été retirée volontairement (voir 3.A).
- Chaîne **« Docteur Shark 🩻 »** (`UCh67MT8wdzldBv-JDFpYlOQ`) connectée dans Clipoa, en mode local (sans le Worker).

### B. Multi-comptes (nouveau code)
Clipoa garde maintenant plusieurs comptes par réseau, un seul actif.
- `core/social_publisher.py` :
  - `storage/social_accounts.json` contient `accounts[platform]` = compte **actif** (inchangé pour tout l'ancien code) + `accounts["_saved"][platform][clé]` = tous les comptes enregistrés.
  - Clé d'un compte : `channel_id` (YouTube), `open_id`/`username` (TikTok), `ig_user_id` (Instagram), `page_id` (Facebook). Helpers `_account_key`, `_identity_from`, `_account_label`, constante `SAVED_KEY`.
  - `save_account(platform, creds, account_key="")` : un nouveau compte repart d'une fiche vierge (jamais de jeton mélangé) ; avec `account_key` d'un compte non actif, met à jour seulement ce compte.
  - Nouveaux : `switch_account()`, `get_account_config()`, `_active_account_keys()`, `_saved_refresh_token()`. `disconnect_account(platform, account_key="")` retire un compte et active le suivant.
  - Chaque publication enregistre `account_keys` (compte actif au moment de la création) ; `execute_post` publie sur CE compte, même si on change ensuite. Les renouvellements de jeton YouTube/TikTok écrivent dans le bon compte.
  - Google affiche toujours le choix du compte (`prompt=consent select_account`).
- `app.py` : nouvelle route `POST /api/social/switch-account` `{platform, account_key}` ; `/api/social/disconnect` accepte `account_key`.
- `templates/index.html` : bouton **＋** (ajouter un compte), menu déroulant pour changer de compte (dès 2 comptes), **✕** retire le compte affiché, pastilles de publication affichent le nom du compte.
- `tests/test_multi_accounts.py` : 7 tests.
- Sauvegarde des fichiers d'avant dans `backups_multicomptes/`.

### C. TikTok — Sandbox prête, clés à poser
- TikTok for Developers : organisation **Clipoa**, app **Clipoa** (`7711719984922068999`), **Sandbox « Clipoa Sandbox »**.
- Sandbox : Login Kit (Web, redirect `https://clipoa-oauth.clipoa-studio.workers.dev/oauth/tiktok/callback`), Content Posting API avec Direct Post, scopes `user.info.basic`, `video.publish`, `video.upload`, compte test **`docsharkinvest`**.
- Infos de base Sandbox : icône générée, catégorie Entertainment, CGU/confidentialité pointées sur le Worker (`/terms`, `/privacy`).
- Production TikTok : pas encore remplie ni soumise.

### D. Worker Cloudflare `clipoa-oauth`
- Ajout des pages `/terms` et `/privacy` (fonction `legalPage`) directement dans l'éditeur Cloudflare, déployé et testé (200).
- ⚠️ Le code déployé est une version plus courte que `oauth_relay_worker.js` local. Le fichier local contient aussi les routes légales mais **n'a pas été déployé tel quel**. Ne pas écraser le Worker avec le fichier local sans comparer.
- **Aucune clé** sur le Worker (`/oauth/status` → providers tous à false).
- Node/Wrangler ne sont pas installés globalement sur le Mac (un Node portable existe dans `runtime/node`). Le Worker se gère depuis le tableau de bord Cloudflare.

### E. Site public + validation Google
- Organisation GitHub **`clipoa-studio`** (gratuite, appartient à BriceMialon), dépôt **`clipoa-studio/clipoa-studio.github.io`**, GitHub Pages depuis `main`.
- Site en ligne : https://clipoa-studio.github.io/ (accueil), `/privacy.html`, `/terms.html`. Copie locale dans `site_public/`.
- Le site perso `bricemialon.github.io` n'a **pas** été modifié (un essai a été retiré, le dépôt est revenu à l'identique). Clipoa est un projet séparé, ne rien mettre sur le site perso.
- Search Console : propriété `https://clipoa-studio.github.io/` **validée** (fichier `google42d62dcf06720b65.html` à la racine — ne jamais le supprimer).
- Google Auth Platform :
  - Branding : nom Clipoa, e-mail d'assistance, accueil/confidentialité/CGU sur clipoa-studio.github.io, domaine autorisé **clipoa-studio.github.io** (seul domaine). Pas de logo.
  - Accès aux données : `youtube.upload` et `youtube.readonly` déclarés (sensibles).
  - Utilisateur test : brice.mialon01800@gmail.com.
  - **Statut : En production** (plus d'expiration à 7 jours ; écran « app non validée » et 100 comptes max tant que la validation n'est pas faite).
  - Centre de validation : en attente de validation du branding ; « Prepare for verification » pas encore disponible au 24/11 16 h.

### F. Meta — bloqué
- Conditions Meta for Developers acceptées, mais Meta refuse d'envoyer l'e-mail de vérification (3 essais, « Impossible d'envoyer l'e-mail »). Brice réessaiera plus tard ou ajoutera un téléphone vérifié à Facebook.

### G. Dossier détaillé
Document Claude « Clipoa — Dossier de validation (Google, TikTok, Meta) » : https://claude.ai/artifact/3wuQqzsbJNmNAPuYJfcjWU
Il contient les textes de justification Google (en anglais, prêts à coller) et le script plan par plan de la vidéo de démo.

---

## 2. Ce qu'il reste à faire (par ordre)

1. **TikTok** — Brice ajoute dans Cloudflare (`clipoa-oauth` → Paramètres → Variables et secrets) `TT_CLIENT_KEY` et `TT_CLIENT_SECRET` de la Sandbox, puis Déployer. Tester « Brancher TikTok » dans Clipoa avec `docsharkinvest`. (Les secrets se collent par Brice, jamais par un agent.)
2. **Google** — quand le Centre de validation le permet : valider le branding, enregistrer la vidéo de démo (script dans le dossier), la mettre en « Non répertoriée » sur YouTube, soumettre l'accès aux données avec les justifications.
3. **Distribution** — faire que d'autres utilisateurs se connectent sans clé : créer un client OAuth Google « Application de bureau » et l'intégrer par défaut dans Clipoa quand `storage/oauth_apps.json` est vide (YouTube passe par localhost, pas par le Worker). Brice doit encore confirmer ce choix.
4. **TikTok production** — recopier la Sandbox dans Production avec les adresses `clipoa-studio.github.io`, faire vérifier le site dans « URL properties », vidéo de démo, soumettre la revue.
5. **Meta** — débloquer le compte développeur, créer l'app Business Clipoa (Facebook Login for Business, redirect `https://clipoa-oauth.clipoa-studio.workers.dev/oauth/meta/callback`), poser `META_APP_ID`/`META_APP_SECRET` sur le Worker, revue des permissions `instagram_content_publish` et `pages_manage_posts`.
6. **Logo** (optionnel) — ajouter un logo 120×120 dans le branding Google (déclenche aussi la validation).

## 3. Points d'attention
- **A.** Les adresses `*.workers.dev`, `*.github.io`, `*.vercel.app` peuvent être refusées par Google. `clipoa-studio.github.io` est validée dans la Search Console ; si Google la refuse malgré tout, prendre un vrai domaine (le GitHub Student Pack de Brice en donne un gratuit 1 an) et le brancher sur GitHub Pages.
- **B.** Le navigateur intégré de l'app Claude bloque les retours OAuth vers `localhost` : pour tester une connexion YouTube, utiliser Chrome.
- **C.** Ne jamais copier de mot de passe ou de code secret à la place de Brice.
