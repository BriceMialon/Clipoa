# CLAUDE.md — Guide Projet Clipoa (passation & développement)

Ce fichier permet à **Claude** (ou tout autre agent IA) de savoir immédiatement **où se trouve le code**, **où on en est**, **comment modifier le projet**, **tester** et **redémarrer l'application**.

---

## 1. Emplacement & Accès

- **Dossier racine du code** : `/Users/brice/.gemini/antigravity/scratch/shortcrew_clone` (symlink `/Users/brice/Downloads/Shortcrew/clipoa`)
- **URL locale** : `http://localhost:8080`
- **Python (venv)** : `/Users/brice/.gemini/antigravity/scratch/shortcrew_clone/venv/bin/python` (**Python 3.9** — ne jamais mettre de backslash `\` dans une expression `{...}` de f-string).
- **Blender CLI** : `/Applications/Blender.app/Contents/MacOS/Blender` (**Blender 5.3.0** — requiert `image_settings.media_type = 'VIDEO'` avant `file_format = 'FFMPEG'` et `BLENDER_WORKBENCH` en 540×960 @ 12 fps pour un rendu multi-plans 60s en ~45s sans timeout).
- **Antigravity CLI (`agy`)** : `/Applications/Gemini.app/Contents/Helpers/agy` (modèle par défaut : `gemini-4-neon-medium`, bac à sable vide `storage/_agy_sandbox`).
- **Claude CLI** : `~/.local/bin/claude` (bac à sable vide `storage/_claude_sandbox` + `--tools "" --strict-mcp-config` + streaming `stream-json`).
- **Logs serveur** : `/tmp/clipoa_server.log`

> **Règle d'or sécurité** : ne JAMAIS supprimer ni écraser les clés API dans `storage/settings.json` ni les connexions OAuth dans `storage/social_accounts.json`. Le dossier `storage/` est ignoré par Git.

---

## 2. Où on en est (État actuel — 25/11/2026, après la « méthode de production »)

1. **Moteurs IA & Streaming temps réel** :
   - **Claude (`core/claude_bridge.py`)** et **Antigravity (`core/antigravity_bridge.py`)** streament tous les deux les scripts mot-à-mot en direct (SSE `/api/fabrique/generate-script/stream`) en bac à sable vide sans latence ni timeout de 150s.
   - Affichage conditionnel : tant qu'aucune IA n'est branchée, la Fabrique affiche un écran d'accueil simplifié vers Connexions.
   - Quotas **5h + hebdo (7j)** affichés pour **Claude** ET **Antigravity** dans Connexions, avec rafraîchissement automatique après chaque script et chaque job vidéo (`refreshJobs`).
   - Bouton **Changer** disponible sur **Claude**, **Antigravity** (`POST /api/antigravity/switch`) et **ElevenLabs** (`POST /api/elevenlabs/disconnect`).
2. **Fabrique simplifiée & Script mis en forme** :
   - Présentation automatique du script généré en mode **`👁️ Aperçu`** (tableaux HTML stylés, timecodes, pastilles `MUS-xx` / `SFX-xx`, boutons **Copier** sur les prompts) avec bascule instantanée **`✏️ Éditer`**.
   - **Paramètres de script avancés** (`core/script_template.py`, `/api/script-templates`) : l'utilisateur peut importer et choisir son propre template `.md`/`.txt` ; Claude et Antigravity s'y adaptent automatiquement.
   - Estimations temps réel auto-apprenantes (`core/timing_tracker.py`, `GET /api/timings`) sans affichage de tokens : temps estimé et `%` quota s'ajustent dynamiquement selon le moteur (Claude vs Antigravity) et la durée cible.
3. **Rendu 3D Roblox Blender multi-plans + Musique d'ambiance & SFX** :
   - `core/blender_engine.py` (`create_roblox_3d_scene`) génère un vrai film 3D multi-plans (5 zones 3D distinctes, coupes de caméra `CONSTANT`) couvrant **100 % de la durée audio** en **Blender Workbench** (`540×960 @ 12 fps`, lighting `STUDIO`, `MATERIAL` colors, ombres + cavity → ~45s pour 60s de vidéo, zéro timeout).
   - `core/sound_designer.py` (`SoundDesigner.mix_ambient_and_sfx`) génère et mixe localement (100 % FFmpeg, 0 clé API) une **musique d'ambiance adaptée au ton** et des **bruits/effets sonores (SFX)** pilotés par deux cases cochables dans la Fabrique (`#fab-enable-music`, `#fab-enable-sfx`).
4. **Méthode de production Clipoa** (`core/production_method.py`, tirée des séries Drive « Docteur Shark » et « Horreur — Christophe ») — s'applique à TOUS les pipelines (Fabrique, clone, retouche) :
   - **Plan de production** (`production_plan.json` dans chaque dossier de rendu, modifiable) : plans calés sur la **voix réelle** (texte du plan retrouvé dans la transcription), rythme **2-4 s** imposé (découpe/fusion), **twist** détecté (`twist_text` du script ou heuristique phrase-choc), CTA détectés, **bruitages ancrés** (hook, coupes espacées ≥ 10 s, mots « argent/porte/… », twist, CTA ; ≤ 20 ; même son jamais 2× en < 4 s ; silence 0,8 s avant le twist), **mots-clés** (jaune noms/chiffres, rouge danger, vert positif), **cartons** de texte géants (`on_screen_notes` avec `at_phrase`), ambiance `dark|tension|upbeat|calm`.
   - Un style peut surcharger via `plugin["production"]` ou `script["production"]` : `mood`, `music_db`, `shot_min_s`, `shot_max_s`, `sfx_max`, `whoosh_min_gap_s`, `sfx_repeat_gap_s`, `music_cut_before_twist_s`.
   - **Audio** (`SoundDesigner`) : progression d'accords par ambiance + réverbe, **ducking sidechain** sous la voix, musique **coupée juste avant le twist**, voix EQ + compression, bibliothèque de SFX synthétisés (`SFX_LIBRARY`), et WAV **sans musique** en plus.
   - **Montage** (`VideoComposer`) : mots-clés colorés + pop, cartons, **loudnorm -14 LUFS**, x264 `medium` CRF 19 bt709, agrandissement lanczos + netteté du fond Blender, et **`final_short_sans_musique.mp4`** (vidéo copiée, 0 ré-encodage). Le Monteur (vidéos longues) a aussi loudnorm + voix claire + mots-clés.
   - **Blender** : coupes de caméra sur les plans du plan de production (`timed_shots`), variantes de cadrage (`interior_close`, `lake_close`), mouvements BEZIER adoucis, AA 11 + contours ; toujours **540×960 @ 12 fps** Workbench.
   - **Scénariste** : règles de narration (qui/quoi/enjeu en 10 s, liens « alors/mais/sauf que », phrase 2-4 mots avant le twist, morale + question, CTA jamais avant 15 s) + champs JSON `twist_text`, `caption_keywords`, `on_screen_notes`, `visual_storyboard[].text`.
   - **Le Contrôle** : contrôles techniques objectifs (`audit.technique` : LUFS, résolution, plans, plan moyen, bruitages, twist, alertes) + 4 images réparties sur toute la durée.
   - **Retouche** : réutilise le fond Blender déjà rendu + musique/SFX (métadonnées `blender_bg`, `enable_music`, `enable_sfx`, `storyboard_shots`).
   - **Réglages de production par style** (`core/style_plugins.py` : `STARTER_PRODUCTION`, `sanitize_production`, champ `production` des plugins) : Roblox = plans 1,2-3 s ; 2D × Monde 3D = plans 1,8-3 s, sous-titres blancs (pas de couleurs), personnages **2D plats** (`character_style: flat2d`) ; Fête en folie = **un seul mot à la fois** (`caption_mode: one_word`), musique très basse (-22 dB), thème `cinema_gold` (désormais réel, + nouveau `pop_flat`).
   - Mode Nuit + route Gemini (`GeminiStudio.create_short`) passent aussi par la méthode (plan, musique/SFX, Blender multi-plans, version sans musique).
   - Scripts Blender écrits par l'IA : `_patch_blender5_compat` corrige `primitive_cone_add(radius=)` → `radius1=` ; `enforce_render_settings` impose 540×960 @ 12 fps, durée de la voix, jamais Cycles.
   - **Aiguillage IA** : choisir « Claude » = toujours le **Claude CLI** (modèle `opus/sonnet/haiku` déduit du nom, `_claude_family`), jamais Antigravity. Antigravity seulement si choisi explicitement (avant : `claude-opus-5-5-medium` partait sur agy et vidait son quota).
   - **Anciennes tâches / anciens onglets** : `_normalize_engine_params` repasse sur Claude toute tâche `engine=antigravity` + modèle `claude-…` sans `engine_choice` explicite (cas du bouton « Reprendre »). Bandeau « Clipoa a été mis à jour » quand `/api/build` change (onglet resté ouvert sur une ancienne version).
   - **Anti-répétition partout** : `build_da_context` ajoute une RÈGLE D'ORIGINALITÉ (la DA Roblox vient de la vidéo « miroirs couverts / neige », ses exemples ne sont pas des sujets) ; `recent_video_titles()` (core/script_template.py) donne les titres récents à éviter à LeScenariste, Antigravity et Gemini.
   - **Décor sur mesure pour CHAQUE vidéo (même processus pour tous les styles)** : `core/scene_designer.py` demande à l'IA choisie (Claude CLI ou Antigravity) de décrire en JSON le décor de l'histoire (lieux, objets, panneaux, personnages, et par plan : lieu / cadrage / action) ; validé (`_sanitize`) avec repli sur le storyboard (`heuristic_spec`). `BlenderEngine.create_scene_from_spec` assemble l'en-tête + le constructeur `core/blender_kit/scene_kit_bpy.py` (styles `roblox`, `paper2d`, `flat_vector`) ou `scene_kit_explainer_bpy.py` (`explainer2d`, caméra ortho de face, glissés latéraux). `ShortCrewPipeline.render_blender_story` (Fabrique, Mode Nuit, Gemini) ; décor sauvegardé dans `storage/audio/<session>_scene_spec.json`. Ancienne scène fixe = secours seulement.
   - **Bibliothèque 3D** `assets/blender_kit/` : les 37 modèles GLB Docteur Shark (sans le village complet) utilisés par le style Roblox (personnages articulés automatiquement, autocollants de visage aplatis pour Workbench, couleurs en Standard + conversion sRGB→linéaire).
   - **Style de rendu par style** : `production.visual_style` (roblox_3d→roblox, 2d_monde_3d→paper2d, fete_en_folie→flat_vector, explainer_2d→explainer2d) ; un style qui en a un passe toujours par Blender.
   - **Nouveau style « Explainer 2D pastel »** (`explainer_2d`, analyse de la vidéo @rosoai) : vectoriel pastel de face, contours fins, pas de sous-titres (`caption_mode: none`), grandes étiquettes roses (`note_color`), plans 2-6 s, structure « explainer de marque ». Ajouté automatiquement aux installations existantes (sans réajouter un style livré que l'utilisateur a supprimé : `storage/plugins/removed_starters.json`) ; vignette `assets/style_covers/`.
   - **« Même style que cette vidéo »** (`core/style_analyzer.py`) : champ « vidéo d'exemple » de la Fabrique (`/api/make-like`, tâche `style_ref`) et carte « Créer un style à partir d'une vidéo » dans Mes styles (`/api/plugins/from-reference`, tâche `style_only`). L'agent télécharge (yt-dlp, `--ffmpeg-location` pour X/YouTube/TikTok), mesure coupes / plans / débit, fait 2 planches + vignette, transcrit, puis l'IA rédige DA + règles + production et choisit le moteur Blender le plus proche (+ outil probable du créateur). Claude regarde les images via `ClaudeBridge.query_with_images` (dossier isolé, seul l'outil Read autorisé) ; Antigravity = analyse sans images.
   - **Audit non bloquant** : si Claude est indisponible (quota), `QualityController` garde les contrôles techniques et la vidéo n'est pas perdue.
   - **Script IA original** : la DA n'est plus coupée à 3 000 caractères (12 000), consigne « les exemples de la DA sont du style, pas des sujets », et les titres des 12 dernières vidéos/jobs sont donnés à éviter (`_recent_video_titles`) ; plans de 2 à 4 s.
   - **Roblox enrichi (réf. TikTok @fusedintheblankfr)** : visages expressifs par plan (`emotion` : neutral/happy/sad/cry/surprised/scared/angry/smirk ; yeux brillants, sourcils, larmes, joues roses, basculés par échelle 0/1), caméras `face` (très gros plan), `back` (perso retourné vers ce qu'il regarde), `high` (plongée), intérieurs meublés (papier peint rayé crème, parquet, plinthes, sofa, rug, frame, window, bookshelf, pancakes…), météo `weather` snow/rain (flocons en boucle, congères), nuit par lieu (`locations[].time_of_day`, extérieurs teintés bleu, fenêtres/lampes restent lumineuses), fond de sapins + toile de ciel, ombres Workbench plus marquées. Toujours Workbench 540x960@12.
   - **Antigravity : % RESTANT** (`get_quota_summary`) : 0 % + heure de reset dès un « Individual quota reached. Resets in … » (réponse agy ou logs `~/.gemini/antigravity*/`), vrais tokens lus dans `stream-json`, calibrage manuel (bouton « Ajuster » → `POST /api/antigravity/quota`, fichier `storage/antigravity_quota_state.json`).
   - **Mode « Roblox 3D Ciné (haute qualité) »** (starter `roblox_cine`, `visual_style: cine3d`) : moteur three.js des vidéos de référence du Drive (GTAO, bloom de nuit, lumière de contour, étalonnage, visages vivants), dans `core/cine_engine/` (film.html + lib). `core/cine_director.py` : mots Whisper → `timeline.json`, l'IA choisie écrit `shots.js` (API dans `API_DOC`), planche de contrôle + détection de défauts (`cine_render.preview`), 2 tours de correction, rendu 1080x1920@30 (`cine_render.film`, Chrome sans fenêtre via Playwright, ~0,18 s/image sur M1). Épisodes dans `storage/cine_episodes/<session>/`. Repli automatique sur Blender Roblox. Installation en un clic (`core/cine_setup.py` : three.js depuis npm, polices, Chrome ou Chromium) → `storage/cine_runtime/`. Avertissement « 20 à 60 min · ~4× tokens » dans la Fabrique (`pl.heavy`). Aucun nom de chaîne perso dans l'interface (test).
   - **Voix HD gratuite locale** (`core/local_tts.py` + `core/tts_worker/qwen_worker.py`, Qwen3-TTS Apache 2.0) : Python 3.11 isolé `venv_tts` créé par `uv`, installé en un clic depuis la Fabrique ; voix `qwen:<Speaker>` ; lente sur M1 (~1 min / 4 s de voix) donc utilisée en mode Auto seulement si la case « voix HD par défaut » est cochée ; repli Edge-TTS.
  - **Produit multi-utilisateur** : tout ce qui s'installe passe par un bouton dans l'app (pas de Terminal), chemins relatifs à `BASE_DIR`, pas de nom/compte perso dans le code ou l'interface.
5. **Interface épurée** :
   - **Barre supérieure** : la barre **Aide IA** (sélecteur de modèle + champ question + tiroir déroulant vers le bas) remplace « Demande à ton équipe Clipoa » ; en haut à droite s'affichent **ElevenLabs + ses crédits restants**.
   - **Sidebar** : loupe search supprimée à côté du logo Clipoa ; en bas à gauche, Antigravity affiche uniquement le `%`.
   - **Mes vidéos** : bouton `+ Fabriquer` retiré à côté de `▶ Regarder une par une`, et filtre `Avec un style` retiré.
   - **Sous-titres** : carte *Dossier créatif local* et bouton `+ Sauvegarder un Preset` retirés.

---

## 3. Carte des fichiers clés

| Fichier | Rôle |
|---|---|
| `app.py` | Serveur Flask principal (routes UI, `/api/fabrique/*`, `/api/make`, `/api/script-templates`, `/api/timings`, `/api/antigravity/*`, `/api/elevenlabs/*`, `/api/plugins*`, `/api/assistant/help`). |
| `core/claude_bridge.py` | Pont Claude CLI (`query`, `stream_query`, bac à sable `_claude_sandbox`, quotas 5h/7j). |
| `core/antigravity_bridge.py` | Pont Antigravity CLI (`query`, `stream_query`, `switch_account`, quotas 5h + hebdo 7j). |
| `core/script_template.py` | Template 6 sections par défaut + CRUD templates personnalisés + extraction plans (`extract_shots_from_template`) & texte parlé. |
| `core/blender_engine.py` | Rendu 3D Blender 5.3 multi-plans (`create_roblox_3d_scene` en Workbench rapide, `_patch_blender5_compat`, `render_script`). |
| `core/scene_designer.py` + `core/blender_kit/` | Décor sur mesure décrit par l'IA + constructeurs Blender par style ; `assets/blender_kit/` = modèles GLB. |
| `core/production_method.py` | Méthode Clipoa : plan de production (plans calés sur la voix, twist, SFX ancrés, mots-clés, cartons). |
| `core/sound_designer.py` | Mixage FFmpeg local : musique par ambiance + ducking + coupure avant twist + SFX du plan + version sans musique. |
| `core/timing_tracker.py` | Apprentissage des durées réelles par moteur/mode (`storage/timing_history.json`). |
| `core/pipeline.py` | Orchestration vidéo (`create_direct_short`, voix + mix audio + Blender 3D multi-plans + composition FFmpeg + sous-titres). |
| `templates/index.html` & `static/css/liquid-glass.css` | UI complète, barre IA en topbar, aperçu script mis en forme, jauges 5h/7j. |
| `tests/` | 88 tests `unittest` (dont `test_production_method.py`) (`test_clipoa.py`, `test_style_plugins.py`, `test_security_hardening.py`, `test_multi_accounts.py`, validation syntaxe JS `node --check`). |

---

## 4. Tester et redémarrer

### Lancer la suite complète de tests (88 tests)
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
