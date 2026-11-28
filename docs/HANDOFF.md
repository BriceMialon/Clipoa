# HANDOFF — Journal de relais Claude ↔ Antigravity

Mettre à jour **avant de s'arrêter**. Le plus récent en haut. Garder seulement les sujets ouverts : supprimer une entrée quand sa PR est fusionnée.

Modèle :

```
## AAAA-MM-JJ HH:MM — <Claude|Antigravity> — <sujet>
- Branche / PR : claude/<sujet> — #<n> (brouillon|prête|fusionnée)
- En cours : ...
- Fichiers touchés : ...
- Prochaine étape : ...
- Attention : (conflit possible, test cassé, décision attendue de Brice)
```

---

## 2026-11-28 12:40 — Claude — Écran de publication TikTok conforme à la revue + script de démo
- Branche / PR : claude/project-thread-b80lyc — #22 (fusionnée)
- En cours : panneau TikTok dans « Publier » (compte via creator_info, visibilité sans défaut, interactions, contenu commercial, consentement musique), route `GET /api/social/tiktok/creator-info`, `tiktok_options` transmis jusqu'à `_publish_tiktok`. Script d'enregistrement : `docs/TIKTOK_REVIEW_DEMO.md`.
- Fichiers touchés : app.py, core/social_publisher.py, templates/index.html, tests/test_tiktok_publish_ux.py, docs/TIKTOK_REVIEW_DEMO.md
- Prochaine étape : tester sur le Mac avec le compte Sandbox, Brice enregistre la démo ; ensuite vidéo promo.
- Attention : les publications automatiques (Mode Nuit/pilote auto) passent encore sans ces choix (ancien comportement) ; retirer `video.upload` du Worker demande l'accord de Brice.

## 2026-11-28 — Claude — Corrections du moteur vidéo (sous-titres, plans, voix)
- Branche / PR : claude/project-thread-rmd7lj (brouillon)
- Fait : sous-titres = mots du script calés sur Whisper (`core/script_align.py`, branché dans `VideoComposer._extract_word_list`) ; découpe des plans longs selon min/max du style (`production_method.align_shots`, cause du plan de 13,6 s) ; caméras Blender `tilt`, `pov`, chute et assis recadrées (`scene_kit_bpy.py`) ; ElevenLabs : plus d'ajout de voix de la bibliothèque sans le réglage `elevenlabs.add_library_voices`, voix de bibliothèque exclues sur compte gratuit, avertissement « voix de secours » dans la carte de la tâche (`warnings`).
- Exemples refaits (28/11 12:05) : `storage/_exemples_corriges/` (parabole 62,6 s, max_shot 6,36 s ; fête 20,9 s, max_shot 2,82 s ; sous-titres parlés = 100 % des mots du script ; `el_voice_added.json` inchangé, 3 voix).
- Corrigé ensuite (28/11 après-midi) : compte ElevenLabs gratuit → plus de voix copiée de la bibliothèque, voix française gratuite plutôt qu'un accent ; emoji des cartons remplacés par des symboles dessinables ; Blender : persos hors plan cachés, tilt/low recadrés, cadrage à la taille du perso (90 cm, géant), grand mot dans le cadre ; Toon : persos (mains comprises) dans le cadre. Rendus v2/v3 dans `storage/_exemples_corriges/`.
- Prochaine étape : Fête en folie « like = 1 cm » a dérivé vers une pub de salon de coiffure (« diagnostic offert, réserve en bio ») : vérifier si la personnalité du compte (lot personnalités) pousse un CTA commercial.
- Attention : le serveur 8080 tourne depuis le worktree `../cliproll-claude-rmd7lj` (cette branche) avec `CLIPOA_DATA_DIR` = dossier principal ; le relancer depuis `main` une fois la PR fusionnée.
- Attention : 3 voix déjà ajoutées au compte ElevenLabs de Brice (Tenko, Guillaume, Léo) ; ClipRoll ne les supprime pas.

## 2026-11-28 11:58 — Antigravity — Fusion des 6 lots sur `main` (base commune Claude ↔ Antigravity)
- Branche / PR : `main` — fusionné et poussé sur `origin/main` avec l'accord explicite de Brice.
- En cours : **tous les 6 lots validés** (`security-core`, `security-app`, `workers-hardening`, `public-edition`, `ui-polish`, `personalities-competitors`) sont maintenant dans `main` (sans la waitlist). `http://localhost:8080/` tourne directement depuis `main` (`/Users/brice/.gemini/antigravity/scratch/shortcrew_clone`).
- Fichiers touchés : sécurité cœur + `app.py`, Workers sans waitlist, édition `public`, UI (barre IA compacte avec focus auto au clic *Équipe IA*/*Aide*, animations vidéos Accueil & Mes vidéos, KPIs Statistiques, onboarding 8 étapes, bouton *Générer le script* sans icône + remonté, nettoyage ShortCrew), personnalités (`core/personality.py` + `cliproll_personality.js`) + 5 comptes concurrents dans l'onglet Concurrents de `#12`.
- Prochaine étape : Claude et Antigravity repartent exactement du même `main` à jour (`git pull`). Reste à faire : Windows (`install.ps1` / `launcher.py` / `updater.py` / `select.select` Blender), TikTok > 64 Mo, et déploiement Stripe/D1 quand Brice valide.
- Attention : `cliproll.app` est en ligne sur Cloudflare (`https://cliproll.app`, SSL actif) avec `contact@cliproll.app`, `support@cliproll.app` et `brice@cliproll.app` redirigés vers `brice.mialon01800@gmail.com`. Waitlist toujours mise de côté en attente de validation offre/date/RGPD.

## 2026-11-27 — Claude — Règles de relais
- Branche / PR : claude/project-thread-15q7fh (PR à fusionner)
- En cours : rien d'autre.
- Fichiers touchés : AGENTS.md, GEMINI.md, CLAUDE.md, docs/HANDOFF.md
- Prochaine étape : Antigravity lit AGENTS.md à sa prochaine session.
