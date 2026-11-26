# Outil d'Analyse & Rétention ClipRoll — Thread `@jeffar_ai` (8 prompts complets)

Source : `@jeffar_ai` (25 nov. 2026) — `https://x.com/jeffar_ai/status/2125640159710568806`  
Usage ClipRoll : **Phase 1 (dès maintenant)** — pour muscler l'onglet **Statistiques** (`core/channel_stats.py`) et la **Fabrique de scripts** (génération / amélioration / audit avant export).

---

## Les 8 prompts exacts du thread

### 1. The Channel Audit System *(Audit global de la chaîne — Onglet Statistiques)*
> "Act as a short-form retention strategist and faceless channel consultant. Build a complete audit system for my channel. Analyze my opening visual hooks, my last twelve Shorts, my B-roll and caption rhythm, my average percentage viewed, and the comments I get. Design a scorecard for each element, the three biggest retention leaks, a rewritten hook formula, a fixed content mix, and a two-week repair plan in priority order, with one task per day."

### 2. The 1.5-Second Hook Rewrite *(Réécriture d'accroche Evidence + Betrayal)*
> "Act as a retention copywriter for faceless creators stuck under 500 views. Rewrite the opening of my Short so a viewer locks in within 1.5 seconds using Evidence + Betrayal. Analyze my niche, my target viewer, my current opening line, and my visual frame. Design five hook options with a 4-word burned-in caption, a spoken opener under 7 words, and the exact frame-1 visual proof."

### 3. The 130-Word Script Pruner *(Élagage impitoyable du script)*
> "Act as a ruthlessly direct short-form script editor. Strip out all polite intros, slow setups, and filler adjectives from my rough draft below. Cap total spoken words at 130 for a 30-second Short, keep every sentence under 8 words max, and land the core payoff before second 20."

### 4. The 2-Column Mobile Storyboard *(Storyboard 2 colonnes + cuts 3–4 s + safe zones)*
> "Convert my pruned 130-word script into an edit-ready storyboard for mobile editing. Format it as a 2-column table: [Exact B-Roll Clip / Gameplay Visual / 3-to-6 Word Caption] on the left and [Spoken Narration] on the right, forcing a visual cut every 3 to 4 seconds while keeping text inside mobile safe zones."

### 5. The 6-Second Pattern Interrupt Map *(Relances multi-sensorielles toutes les 6 s)*
> "Act as a CapCut retention editor. Audit my storyboard and mark exact timestamps every 6 seconds to insert a multi-sensory pattern interrupt—combining a zoom punch, screen shake, or graphic pop with a crisp sound effect (swoosh, pop, bass drop) to reset viewer attention."

### 6. The Voice Pacing & Breath Formatter *(Rythme voix ElevenLabs / TTS)*
> "Rewrite my script for high-energy faceless narration. Remove robotic transitions, add natural micro-pauses, and emphasize key tension words so the delivery feels urgent and human rather than flat."

### 7. The Seamless Loop & Comment Trigger *(Boucle >100 % watch time + déclencheur commentaires)*
> "Rewrite the final 2 lines of my script to push watch time past 100%. First, add a polarizing binary question that forces a 1-word comment (AGREE or DISAGREE). Second, connect the final spoken syllable grammatically back into my opening hook with zero pause."

### 8. The Pre-Upload Swipe-Away Audit *(Audit anti-swipe avant export)*
> "Audit my final script and storyboard before I export. Flag the exact second where viewers are most likely to swipe away, explain why momentum drops there, and give me a final 5-point checklist before uploading."

---

## Plan d'intégration concret dans ClipRoll

1. **Onglet Statistiques (`core/channel_stats.py`)** :
   - Ajouter un bloc **« Audit global de ta chaîne (12 derniers Shorts) »** en haut de l'onglet Statistiques (alimenté par le Prompt #1) qui affiche :
     - Scorecard sur 100 par pilier (Accroche 1.5s, Rythme/Durée, Engagement/Commentaires, Régularité).
     - **Les 3 plus grosses fuites de rétention** détectées sur la chaîne active (YouTube OU TikTok).
     - **Nouvelle formule d'accroche recommandée** + **Plan d'action 7/14 jours** (1 action concrète par vidéo).
   - Bouton **« Refaire la vidéo avec l'IA »** : injecter automatiquement les contraintes des Prompts #2 (Hook 1.5s Evidence + Betrayal), #3 (phrases < 8 mots, payoff < 20s) et #7 (boucle parfaite + question binaire pour commentaires) dans `remake_request()`.

2. **Onglet Créer — Fabrique de script** :
   - Ajouter un bouton optionnel **« Optimiser la rétention »** (ou passe automatique) qui applique :
     - **Hook 1.5s** (5 variantes avec texte incrusté ≤ 4 mots + phrase parlée < 7 mots + preuve visuelle frame 1).
     - **Élagage** (zéro intro molle, phrases courtes, densité cible ~130 mots / 30 s).
     - **Formatage voix ElevenLabs** (micro-pauses naturelles, mots de tension accentués).
     - **Boucle finale + question binaire** (pousser les commentaires et le watch time > 100 %).
   - Ajouter une **passe « Audit anti-swipe »** (Prompt #8) juste avant le bouton `Fabriquer` pour signaler la seconde la plus risquée du script.

3. **Moteur de montage 9:16** :
   - S'assurer que les **pattern interrupts** (zoom punch, léger shake, pop visuel + SFX swoosh/pop/bass drop) sont bien cadencés **toutes les 6 secondes** (Prompt #5) avec des changements de plan toutes les **3 à 4 secondes** et les sous-titres dans les **safe zones mobiles** (Prompt #4).
