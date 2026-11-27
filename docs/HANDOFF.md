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

## 2026-11-27 21:06 — Antigravity — Lot 4 Édition public
- Branche / PR : `gemini/public-edition` — PR brouillon (prête à relire)
- En cours : renforcement édition `public` par-dessus #11 et #14 (`requires_license()` élargi, `license.json` `0o600`, `deactivate(force=False)`, `NightFactory.start_worker()` coupé en `public` + fix ISO `"Z"`, `browser_session:` coupé en `public`, filtrage plugins `heavy`, `competitor_url` / Gemini coupés sur `/api/script-lab/generate`), sans toucher à `static/js/cliproll_license.js` (#11 déjà complet).
- Fichiers touchés : `app.py`, `core/license.py`, `core/night_factory.py`, `core/social_publisher.py`, `tests/test_public_edition.py`, `docs/HANDOFF.md`
- Prochaine étape : Lot 5 (UI animations vidéos / KPIs / onboarding / nettoyage ShortCrew) puis Lot 6 (Personnalités + 5 comptes concurrents dans l'onglet Concurrents de #12).
- Attention : PR 1 (`gemini/security-core`), PR 2 (`gemini/security-app`) et PR 3 (`gemini/workers-hardening`) déjà poussées.

## 2026-11-27 — Claude — Règles de relais
- Branche / PR : claude/project-thread-15q7fh (PR à fusionner)
- En cours : rien d'autre.
- Fichiers touchés : AGENTS.md, GEMINI.md, CLAUDE.md, docs/HANDOFF.md
- Prochaine étape : Antigravity lit AGENTS.md à sa prochaine session.
