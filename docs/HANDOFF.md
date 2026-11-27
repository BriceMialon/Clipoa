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

## 2026-11-27 21:02 — Antigravity — Lot 2 Sécurité app.py
- Branche / PR : `gemini/security-app` — PR brouillon (prête à relire)
- En cours : durcissement sécurité `app.py` seul (`_is_safe_id` / `_safe_render_dir`, ordre `_security_guard`, CSRF `Origin: null` / Referer, LAN token `/oauth/*/start`, `relay-done` POST-only + provider check, `/api/thumb` MIME strict + 5 Mo stream, SVG en attachment + `CSP: sandbox`), rebasé sur `origin/main` (`0b4e932`).
- Fichiers touchés : `app.py`, `tests/test_security_app.py`, `docs/HANDOFF.md`
- Prochaine étape : Lot 4 (Édition `public`), Lot 5 (UI carrousels / KPIs / onboarding / nettoyage ShortCrew), Lot 6 (Personnalités + 5 concurrents dans la vue `analyse` de #12).
- Attention : PR 1 (`gemini/security-core`) et PR 3 (`gemini/workers-hardening`) déjà poussées et prêtes à ouvrir/fusionner.

## 2026-11-27 — Claude — Règles de relais
- Branche / PR : claude/project-thread-15q7fh (PR à fusionner)
- En cours : rien d'autre.
- Fichiers touchés : AGENTS.md, GEMINI.md, CLAUDE.md, docs/HANDOFF.md
- Prochaine étape : Antigravity lit AGENTS.md à sa prochaine session.
