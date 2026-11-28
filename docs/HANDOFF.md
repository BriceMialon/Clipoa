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

## 2026-11-28 11:48 — Antigravity — Lot 5 UI (tiroir Équipe IA/Aide compact, Créer remonté sans icône, Concurrents épuré, animations vidéos, KPIs, onboarding 8 étapes)
- Branche / PR : `gemini/ui-polish` — PR brouillon (à fusionner dans `main` avec Lots 1–4 et Lot 6 pour que les redémarrages depuis `main` conservent tout !)
- En cours : portage propre sur `origin/main` (`0b4e932`) + nouveaux ajustements de Brice : tiroir *Équipe IA* / *Aide* compact avec 3 exemples courts (plus de `#ai-roster-strip` ni pavé d'accueil), `#ai-tb-model` supprimé, bouton *Générer le script avec l'IA* sans icône + remonté sur la même ligne que `#fab-ref-url`, sous-titre *Analyse des concurrents* retiré, défilement fluide *À valider* (Accueil) + vitrine 9:16 animée *Mes vidéos*, bouton unique *Statistiques* + 6 KPIs, *Publier*/*Montage* nettoyés, onboarding 8 étapes, nettoyage ShortCrew.
- Fichiers touchés : `templates/index.html`, `static/css/cliproll.css`, `static/js/cliproll_onboarding.js`, `static/js/cliproll_support.js`, `cli.py`, `core/video_composer.py`, `ShortCrew.command` (supprimé), `docs/HANDOFF.md`
- Prochaine étape : fusionner les 6 PR (`security-core`, `security-app`, `workers-hardening`, `public-edition`, `ui-polish`, `personalities-competitors`) dans `main` dès validation de Brice, afin qu'un redémarrage depuis `main` garde tout.
- Attention : `http://localhost:8080/` tourne sur `/Users/brice/.gemini/antigravity/scratch/cliproll-preview` (`gemini/preview-all-lots`) qui combine `main` + les 6 lots.

## 2026-11-27 — Claude — Règles de relais
- Branche / PR : claude/project-thread-15q7fh (PR à fusionner)
- En cours : rien d'autre.
- Fichiers touchés : AGENTS.md, GEMINI.md, CLAUDE.md, docs/HANDOFF.md
- Prochaine étape : Antigravity lit AGENTS.md à sa prochaine session.
