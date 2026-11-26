# CLAUDE.md — Guide Projet Clipoa (passation & développement)

Ce fichier permet à **Claude** (ou tout autre agent IA) de savoir immédiatement **où se trouve le code**, **où on en est**, **comment modifier le projet**, **tester** et **redémarrer l'application**.

---

## 1. Emplacement & Accès

- **Dossier racine du code** : `/Users/brice/.gemini/antigravity/scratch/shortcrew_clone` (symlink `/Users/brice/Downloads/Shortcrew/clipoa`)
- **URL locale** : `http://localhost:8080`
- **Python (venv)** : `/Users/brice/.gemini/antigravity/scratch/shortcrew_clone/venv/bin/python` (**Python 3.9** — ne jamais mettre de backslash `\` dans une expression `{...}` de f-string).
- **Blender CLI** : `/Applications/Blender.app/Contents/MacOS/Blender` (**Blender 5.3.0** — requiert `image_settings.media_type = 'VIDEO'` avant `file_format = 'FFMPEG'` et `BLENDER_WORKBENCH` en 540×960 @ 12 fps pour un rendu multi-plans 60s en ~45s sans timeout).
- **Claude CLI** : `~/.local/bin/claude` (bac à sable vide `storage/_claude_sandbox` + `--tools "" --strict-mcp-config` + streaming `stream-json`).
- **Logs serveur** : `/tmp/clipoa_server.log`

> **Règle d'or sécurité** : ne JAMAIS supprimer ni écraser les clés API dans `storage/settings.json` ni les connexions OAuth dans `storage/social_accounts.json`. Le dossier `storage/` est ignoré par Git.

---

## 2. État et règles (résumé — le détail est dans `docs/HISTORIQUE.md`)

- **Produit** : app Flask locale qui fabrique des shorts (script IA → voix → plan de production → décor Blender → montage FFmpeg → publication). Styles livrés : Roblox 3D, Stickman, Explainer 2D, Fête en folie, Ciné (three.js).
- **Mise en ligne décidée (26/11/2026)** : rendu en LOCAL chez chaque utilisateur (app installable Mac puis Windows), chaque utilisateur branche SA propre IA (clé API Anthropic par défaut, `core/anthropic_api.py`), abonnement vérifié par licence signée + relais OAuth réservé aux abonnés. Plan complet : https://claude.ai/artifact/5yjk1RkhEWqRjMJRFogR3E
- **Version publique** : `CLIPOA_EDITION=public` (`core/edition.py`) coupe côté serveur Gemini, Mode Nuit/Pilote auto, Ciné, moteurs sur mesure, radar, copie de vidéo, connexion par cookies. Défaut `perso` = tout actif. Toute nouvelle fonction risquée (CGU, code exécuté, données de tiers) doit y être rattachée.
- **Code IA exécuté** : le code bpy écrit par l'IA passe par `core/code_guard.py` avant Blender. Ne jamais exécuter du code IA sans ce contrôle.
- **Multi-utilisateur / portable** : pas de chemin ni de nom perso dans le code, chemins relatifs à `BASE_DIR`, tout s'installe par un bouton, pas de nouveau `.command` ni d'AppleScript (portage Windows prévu).
- **Tests** : 111+ tests `unittest` ; lancer ceux du module touché avant de commiter.
- **Historique** : ajouter le détail d'une nouveauté dans `docs/HISTORIQUE.md` (pas ici). Ce fichier doit rester sous ~6 Ko : il est lu à chaque session d'agent.

---

## 3. Carte des fichiers clés

| Fichier | Rôle |
|---|---|
| `app.py` | Serveur Flask principal (routes UI, `/api/fabrique/*`, `/api/make`, `/api/script-templates`, `/api/timings`, `/api/elevenlabs/*`, `/api/plugins*`, `/api/assistant/help`). |
| `core/claude_bridge.py` | Pont Claude CLI (`query`, `stream_query`, bac à sable `_claude_sandbox`, quotas 5h/7j). |
| `core/anthropic_api.py` | Claude par la clé API de l'utilisateur (test sans tokens, texte, streaming, images) ; choisi par `ClaudeBridge._api_mode()`. |
| `core/license.py` + `license_worker/` | Abonnement Stripe (Worker Cloudflare + D1) et licence signée Ed25519 vérifiée hors ligne ; fabrication bloquée (402) sans licence en édition public. |
| `core/edition.py` | Édition `perso` / `public` (fonctions coupées côté serveur). |
| `core/code_guard.py` | Contrôle du code Blender écrit par l'IA avant exécution. |
| `core/crash_report.py` | Rapports de plantage + contact support (capture locale, secrets masqués, envoi au clic vers le relais `/support/report`, voir `docs/SUPPORT.md`). |
| `core/script_template.py` | Template 6 sections par défaut + CRUD templates personnalisés + extraction plans (`extract_shots_from_template`) & texte parlé. |
| `core/blender_engine.py` | Rendu 3D Blender 5.3 multi-plans (`create_roblox_3d_scene` en Workbench rapide, `_patch_blender5_compat`, `render_script`). |
| `core/scene_designer.py` + `core/blender_kit/` | Décor sur mesure décrit par l'IA + constructeurs Blender par style ; `assets/blender_kit/` = modèles GLB. |
| `core/production_method.py` | Méthode Clipoa : plan de production (plans calés sur la voix, twist, SFX ancrés, mots-clés, cartons). |
| `core/sound_designer.py` | Mixage FFmpeg local : musique par ambiance + ducking + coupure avant twist + SFX du plan + version sans musique. |
| `core/notifier.py` + `core/menubar.py` | Notifications macOS (vidéo prête, publiée) + icône barre de menus (état, Ouvrir, Quitter). |
| `core/timing_tracker.py` | Apprentissage des durées réelles par moteur/mode (`storage/timing_history.json`). |
| `core/pipeline.py` | Orchestration vidéo (`create_direct_short`, voix + mix audio + Blender 3D multi-plans + composition FFmpeg + sous-titres). |
| `templates/index.html` & `static/css/liquid-glass.css` | UI complète, barre IA en topbar, aperçu script mis en forme, jauges 5h/7j. |
| `tests/` | 111 tests `unittest` (dont `test_production_method.py`) (`test_clipoa.py`, `test_style_plugins.py`, `test_security_hardening.py`, `test_multi_accounts.py`, validation syntaxe JS `node --check`). |

---

## 4. Tester et redémarrer

### Lancer la suite complète de tests (111 tests)
```bash
cd /Users/brice/.gemini/antigravity/scratch/shortcrew_clone
./venv/bin/python -m unittest discover -s tests -v
```

### Redémarrer Clipoa proprement sur `localhost:8080`
```bash
lsof -ti :8080 | xargs kill -9 2>/dev/null || true
cd /Users/brice/.gemini/antigravity/scratch/shortcrew_clone
nohup ./venv/bin/python app.py > /tmp/clipoa_server.log 2>&1 &
sleep 3 && curl -s -o /dev/null -w "HTTP %{http_code}\n" http://127.0.0.1:8080/
```

