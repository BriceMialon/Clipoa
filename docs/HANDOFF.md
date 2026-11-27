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

## 2026-11-27 18:32 — Antigravity — Lot 3 Workers (sans waitlist)
- Branche / PR : `gemini/workers-hardening` — PR brouillon (prête à relire)
- En cours : durcissement des Workers Cloudflare (`license_worker/` + `oauth_relay_worker.js`) sans waitlist, en conservant 100 % du `licenseGate` et du fix TikTok de `main`.
- Fichiers touchés : `license_worker/worker.js`, `license_worker/schema.sql`, `license_worker/wrangler.toml.example`, `oauth_relay_worker.js`, `docs/HANDOFF.md`
- Prochaine étape : Lot 2 (`app.py` sécurité) puis Lots 4, 5 (UI carrousels), 6 (Personnalités + 5 concurrents).
- Attention : aucune route ni table waitlist incluse dans cette PR.

## 2026-11-27 — Claude — Règles de relais
- Branche / PR : claude/project-thread-15q7fh (PR à fusionner)
- En cours : rien d'autre.
- Fichiers touchés : AGENTS.md, GEMINI.md, CLAUDE.md, docs/HANDOFF.md
- Prochaine étape : Antigravity lit AGENTS.md à sa prochaine session.
