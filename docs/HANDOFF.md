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
