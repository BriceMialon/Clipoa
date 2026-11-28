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

## 2026-11-28 — Claude — Corrections du moteur vidéo (sous-titres, plans, voix)
- Branche / PR : claude/project-thread-rmd7lj (brouillon)
- Fait : sous-titres = mots du script calés sur Whisper (`core/script_align.py`, branché dans `VideoComposer._extract_word_list`) ; découpe des plans longs selon min/max du style (`production_method.align_shots`, cause du plan de 13,6 s) ; caméras Blender `tilt`, `pov`, chute et assis recadrées (`scene_kit_bpy.py`) ; ElevenLabs : plus d'ajout de voix de la bibliothèque sans le réglage `elevenlabs.add_library_voices`, voix de bibliothèque exclues sur compte gratuit, avertissement « voix de secours » dans la carte de la tâche (`warnings`).
- Prochaine étape : refaire les exemples Parabole et Fête en folie avec ce moteur (PR #19 et #20 à remplacer).
- Attention : 3 voix déjà ajoutées au compte ElevenLabs de Brice (Tenko, Guillaume, Léo) ; ClipRoll ne les supprime pas.

## 2026-11-27 — Claude — Règles de relais
- Branche / PR : claude/project-thread-15q7fh (PR à fusionner)
- En cours : rien d'autre.
- Fichiers touchés : AGENTS.md, GEMINI.md, CLAUDE.md, docs/HANDOFF.md
- Prochaine étape : Antigravity lit AGENTS.md à sa prochaine session.
