# CLAUDE.md — Guide Projet Clipoa (passation & développement)

Ce fichier permet à **Claude** (ou tout autre agent IA) de savoir immédiatement **où se trouve le code**, **où on en est**, **comment modifier le projet**, **tester** et **redémarrer l'application**.

---

## 1. Emplacement & Accès

- **Dossier racine du code** : `/Users/brice/.gemini/antigravity/scratch/shortcrew_clone`
- **URL locale** : `http://localhost:8080`
- **Python (venv)** : `/Users/brice/.gemini/antigravity/scratch/shortcrew_clone/venv/bin/python` (**Python 3.9** — ne jamais mettre de backslash `\` dans une expression `{...}` de f-string).
- **Node (validation JS)** : `/Users/brice/.gemini/antigravity/scratch/shortcrew_clone/runtime/node/bin/node`
- **Logs serveur** : `/Users/brice/.gemini/antigravity/scratch/shortcrew_clone/storage/server.log`

> **Règle d'or sécurité** : ne JAMAIS supprimer ni écraser les clés API dans `storage/settings.json` ni les connexions OAuth dans `storage/social_accounts.json`.

---

## 2. Où on en est (État actuel)

1. **Docteur Shark supprimé à 100 %** : plus aucun fichier, module, route (`/api/docshark/*`), ni texte dans l'interface.
2. **Système de Plugins de Style (DA)** opérationnel (`core/style_plugins.py`, routes `/api/plugins*`, vue `Plugins DA`, modale 4 onglets Identité / Planches / Script / DA Claude).
   - 3 styles intégrés prêts avec aperçu visuel, Style Bible complète, estimation temps + tokens/quota (calibrée sur **1 minute** et ajustée dynamiquement selon la durée choisie) :
     - **`3D Roblox`** (`id: "roblox_3d"`, image `storage/plugins/roblox_3d/sheets/roblox_3d.jpg`) — *In this town / Dans ma ville* (variantes A Pop & B Mélancolie).
     - **`2D × Monde 3D`** (`id: "2d_monde_3d"`, image `storage/plugins/2d_monde_3d/sheets/2d_monde_3d.jpg`) — *Conte cartoon 2D dans un monde 3D*.
     - **`Fête en folie`** (`id: "fete_en_folie"`, image `storage/plugins/fete_en_folie/sheets/fete_en_folie.jpg`) — *La Tour des Riches* (flat vector 2D saturé, sous-titres 1 mot au centre, UI TikTok intégrée).
   - L'utilisateur peut toujours basculer entre **« À partir d'une idée »** et **« J'ai mon script »** (texte conservé mot pour mot avec application de la DA choisie).
3. **Sélecteur de durée cible** (`30s`, `45s`, `1 min`, `1m30`, `2 min`) dans la Fabrique & le Script Lab : pilote la longueur du script (`duration_to_word_range`) et ajuste en direct le temps estimé et le coût en tokens/quota.
4. **Barre des tâches Aide IA** en bas de l'écran (`#ai-taskbar`, route `POST /api/assistant/help`) :
   - Active dès que Claude ou Gemini est connecté dans « Connexions ».
   - Sélecteur de modèle intégré (`Claude Sonnet / Opus / Haiku`, `Gemini 3 Flash / 3.8 Flash / 3.1 Pro`) pour choisir quel modèle répond et guide l'utilisateur sur Clipoa.

5. **Refonte UI 2.0 (25/11/2026)** — `static/css/clipoa-ui.css` (chargé après `liquid-glass.css`) : verre dépoli + fond aurore, mode **Clair / Sombre** (sélecteur dans la barre latérale, `?theme=light|dark` dans l'URL), accent dégradé corail → rose.
   - Navigation 5 + 2 : Accueil · Créer · Mes vidéos · Publier · Statistiques | Réglages : Styles · Connexions.
   - Rubriques à onglets (`.subnav`) : **Créer** = `creer` / `montage` / `analyse` / `equipe` ; **Styles** = `plugins` / `style`. Mapping JS `VIEW_GROUP` dans `showView()`.
   - `?open=<vue>` ouvre n'importe quelle vue. Les presets sont dans le tiroir « Personnaliser » de la Fabrique.

---

## 3. Carte des fichiers clés

| Fichier | Rôle |
|---|---|
| `app.py` | Serveur Flask principal (routes UI, `/api/plugins*`, `/api/make`, `/api/gemini/*`, `/api/script-lab/*`, `/api/assistant/help`, jobs). |
| `core/style_plugins.py` | `STARTER_PLUGINS`, Style Bibles, `StylePluginStore` (CRUD, planches, scripts), `duration_to_word_range()`, `estimate_plugin_cost_and_time()`. |
| `core/claude_bridge.py` | Pont vers Claude CLI / API Anthropic (`ClaudeBridge.query(..., model=...)`, quotas 5h). |
| `core/gemini_studio.py` | Studio Google Gemini (`query`, `chat_text`, `create_short`, quotas). |
| `core/pipeline.py` | Orchestration vidéo complète (`create_short`, `create_short_from_script`, `target_duration_sec`). |
| `core/night_factory.py` | File d'attente Mode Nuit. |
| `agents/team.py` & `agents/script_expert.py` | Agents IA scénariste & Script Lab (injection DA + durée cible). |
| `templates/index.html` | Toute l'interface web + JS inline (vues Accueil, Fabrique, Plugins DA, Vidéos, Connexions, Barre des tâches Aide IA). |
| `static/css/liquid-glass.css` | Styles Liquid Glass (dont plugins DA, barre de durée, barre des tâches Aide IA). |
| `storage/plugins/` | Index `plugins.json` + dossiers `<plugin_id>/sheets/` et `<plugin_id>/scripts/`. |
| `tests/` | Suite `unittest` (`test_style_plugins.py`, `test_security_hardening.py`, etc. dont validation syntaxe JS via `node --check`). |

---

## 4. Comment modifier, tester et mettre à jour

### Ajouter ou modifier un Style DA intégré
1. Éditer `STARTER_PLUGINS` dans `core/style_plugins.py`.
2. Placer l'image d'aperçu dans `storage/plugins/<id>/sheets/<id>.jpg`.
3. Supprimer `storage/plugins/plugins.json` (pour re-seeder proprement au démarrage) ou mettre à jour via `PUT /api/plugins/<id>`.

### Lancer toute la suite de tests (obligatoire après chaque modif)
```bash
cd /Users/brice/.gemini/antigravity/scratch/shortcrew_clone
./venv/bin/python -m unittest discover -s tests -v
```

### Redémarrer Clipoa sur `localhost:8080`
```bash
cd /Users/brice/.gemini/antigravity/scratch/shortcrew_clone
pkill -f "shortcrew_clone/app.py" || lsof -ti :8080 | xargs -r kill
nohup ./venv/bin/python app.py > storage/server.log 2>&1 < /dev/null &
sleep 2
curl -s http://127.0.0.1:8080/api/system/health
```

### Mettre à jour ce fichier
Après chaque ajout ou changement important (nouveau style, nouvelle vue, nouvelle route API), mets à jour la section **« 2. Où on en est »** ci-dessus pour garder la mémoire partagée toujours à jour.
