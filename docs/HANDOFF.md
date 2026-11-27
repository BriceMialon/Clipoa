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

## 2026-11-27 21:18 — Antigravity — Lot 6 Personnalités + 5 concurrents (dans l'onglet Concurrents de #12)
- Branche / PR : `gemini/personalities-competitors` — PR brouillon (prête à relire)
- En cours : système de personnalités (Créateur / Entreprise / Personnalités personnalisées CRUD `/api/personalities`, flag `private_owner` filtré en `public`, injection prompt `script_template.py` + `agents/team.py`) + suivi des 5 comptes concurrents (`>= 2×` vues, brief recette structurelle) injecté dans la vue `analyse` (onglet Concurrents de `#12`, coupé en `public`). Sans waitlist.
- Fichiers touchés : `core/personality.py`, `static/js/cliproll_personality.js`, `app.py`, `core/edition.py`, `core/script_template.py`, `agents/team.py`, `templates/index.html`, `tests/test_personalities_competitors.py`, `docs/HANDOFF.md`
- Prochaine étape : validation & fusion des 6 PR brouillons (`security-core`, `security-app`, `workers-hardening`, `public-edition`, `ui-polish`, `personalities-competitors`).
- Attention : aucune route waitlist dans cette PR.

## 2026-11-27 — Claude — Règles de relais
- Branche / PR : claude/project-thread-15q7fh (PR à fusionner)
- En cours : rien d'autre.
- Fichiers touchés : AGENTS.md, GEMINI.md, CLAUDE.md, docs/HANDOFF.md
- Prochaine étape : Antigravity lit AGENTS.md à sa prochaine session.
