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

## 2026-11-28 13:10 — Claude — Style « Carte animée » (géographie)
- Branche / PR : claude/project-thread-u5zcp0 (brouillon)
- En cours : nouveau style `carte_geo` (moteur Geo Kit MIT téléchargé au premier usage, voir HISTORIQUE). Rendu d'exemple sur le Mac dans le worktree `../cliproll-claude-geo`.
- Fichiers touchés : core/geo_engine.py, core/geo_kit_manifest.json, core/style_plugins.py, core/pipeline.py, core/production_method.py, tests/test_geo_map.py, assets/style_covers/carte_geo.jpg, assets/style_refs/carte_geo.mp4
- Prochaine étape : avis de Brice sur l'exemple ; choix Haute qualité/Rapide pas encore proposé dans la Fabrique pour ce style (index.html non touché).
- Attention : le test « chaque style livré a un exemple » échoue tant que assets/style_refs/carte_geo.mp4 n'est pas commité.

## 2026-11-28 13:20 — Antigravity — Préparation lancement ClipRoll + soumission TikTok
- Branche / PR : `main` (à pousser après validation de Brice)
- Fait :
  - **TikTok Developers** (`App ID: 7711719984922068999`) : domaine `cliproll.app` vérifié par DNS Cloudflare, logo `1024×1024`, Login Kit (`user.info.basic`) + Content Posting API (`video.upload` + Direct Post `video.publish`), vidéo démo Sandbox sous-titrée en anglais (`cliproll_tiktok_review_demo.mp4`), **soumis et en statut `In review`**.
  - **Barre de fabrication 15 s** (`8c57ca1`, poussé sur `origin/main`) : auto-masquage après 15 s hors Fabrique + bouton « Voir dans Fabrique ».
  - **Correctifs lancement** :
    - `core/blender_engine.py` : remplacement de `select.select` par un thread lecteur + `queue.Queue` (corrige le crash Blender sous Windows).
    - `core/social_publisher.py` : `tiktok_chunk_plan` conforme à la spec TikTok pour les vidéos > 64 Mo (chunks de 10 Mo, `floor`, dernier chunk absorbe le reste `<= 128 Mo`, plus de dernier chunk < 5 Mo rejeté).
    - `storage/settings.json` local : personnalité remise sur `creator` (c'est le mode `business` / `Atelier Nuance` resté actif qui avait injecté le CTA coiffeur dans le test `Fête en folie`).
- Fichiers touchés : `core/blender_engine.py`, `core/social_publisher.py`, `tests/test_tiktok_publish_ux.py`, `docs/HANDOFF.md`
- Prochaine étape :
  - Attendre la validation TikTok (`In review`, mail sur `bricemialonpro@gmail.com`).
  - Meta for Developers : verrou de confiance « appareil inhabituel » en cours (réessayer dans 2–3 jours pour Instagram Reels / Facebook).
  - Déploiement Stripe / D1 + waitlist quand Brice valide l'offre et les dates.
- Attention : `http://localhost:8080/` tourne désormais directement depuis `main` (`/Users/brice/.gemini/antigravity/scratch/shortcrew_clone`).
