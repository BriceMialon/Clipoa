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

## 2026-11-27 21:12 — Antigravity — Lot 5 UI (animations vidéos, KPIs Statistiques, onboarding 8 étapes, nettoyage ShortCrew)
- Branche / PR : `gemini/ui-polish` — PR brouillon (prête à relire)
- En cours : portage propre sur `origin/main` (`0b4e932`) des améliorations UI demandées par Brice : retrait `#ai-tb-model`, défilement fluide *À valider* (Accueil), vitrine 9:16 animée *Mes vidéos* (`#lib-showcase`), bouton unique *Statistiques* + 6 KPIs, *Publier*/*Montage* nettoyés, onboarding 8 étapes (`cliproll_onboarding.js`), nettoyage derniers noms ShortCrew/Clipoa (`ShortCrew.command` supprimé, `cli.py`, `core/video_composer.py`, `cliproll_support.js`).
- Fichiers touchés : `templates/index.html`, `static/css/cliproll.css`, `static/js/cliproll_onboarding.js`, `static/js/cliproll_support.js`, `cli.py`, `core/video_composer.py`, `ShortCrew.command` (supprimé), `docs/HANDOFF.md`
- Prochaine étape : Lot 6 (Personnalités + 5 comptes concurrents dans la vue `analyse` de `#12`).
- Attention : PR 1 (`gemini/security-core`), PR 2 (`gemini/security-app`), PR 3 (`gemini/workers-hardening`) et PR 4 (`gemini/public-edition`) déjà poussées.

## 2026-11-27 — Claude — Règles de relais
- Branche / PR : claude/project-thread-15q7fh (PR à fusionner)
- En cours : rien d'autre.
- Fichiers touchés : AGENTS.md, GEMINI.md, CLAUDE.md, docs/HANDOFF.md
- Prochaine étape : Antigravity lit AGENTS.md à sa prochaine session.
