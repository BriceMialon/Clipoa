# Setup Agent : Protocole J.A.R.V.I.S. (`@profpicsou`) & Système SEO KB (`@timseo_`)

Sources analysées :
- `@profpicsou` (26 nov. 2026) — Tweet + vidéo complète 1m20 (*« Mon J.A.R.V.I.S. »*) + commentaires (`https://x.com/profpicsou/status/2125866293580448144`)
- `@timseo_` (25 nov. 2026) — Infographie *« Comment créer un système pour automatiser correctement ton SEO »* (`https://x.com/timseo_/status/2125631851427426532`)

---

## 1. Architecture multi-agents de `@profpicsou` (vidéo 1m20)

### Règle d'or
> **Un agent = un métier.** Dès qu'un agent fait tout, il fait tout moyennement.

### L'équipe (6 agents + 1 orchestrateur)
- **Utilisateur → ne parle qu'à l'orchestrateur (`Tamil`)** : comprend, découpe, délègue, vérifie, recommande.
- **5 spécialistes** :
  1. **Tamila (Avocat du diable)** : cherche les risques, failles, contre-arguments et alternatives. (*« Tamila démonte, Tamil tranche, je décide »*).
  2. **Plume (Veille & voix)** : veille X 2×/jour en semaine + rédaction dans la voix exacte de l'utilisateur.
  3. **Dossier (Analyste)** : thèse, antithèse, journal des décisions.
  4. **Socrate (Prof)** : pose des questions pour faire progresser sur un sujet de fond, ne donne pas les réponses toutes faites.
  5. **Boussole (Logistique / Voyages)** : itinéraires, transports, budget.

### Une IA par métier (boîte à outils)
- **Hermès** : prospection terrain (trouver, qualifier, approcher).
- **ChatGPT Work** : articles longs, structurés, sources vérifiées.
- **Outil data** : Search Console, Shopify, Meta Ads.
- **Claude** : le créatif (vidéo, pixel art, motion design).
- *Principe clé* : **le vrai gain est de savoir quelle IA appeler pour quoi**, et de combiner *terrain + contre-avis*.

### Process d'écriture & vérification (5 étapes)
1. **L'idée** (humain ou veille).
2. **Vérification** : remonter à la **source primaire**, contrôler chaque chiffre (ex. une note J.P. Morgan mal résumée ou une rumeur virale sourcée sur un simple commentaire de blog -> marquée `RUMEUR`).
3. **Dans sa voix** : aucun chiffre sans source, sources citées.
4. **Le fond** : modèle dédié aux articles longs.
5. **Publication** : *Rien ne part sans validation humaine. Jamais.*

### Le protocole J.A.R.V.I.S. (cycle fixe 8 étapes + 3 mécanismes)
Cycle pour chaque mission :
`Comprendre → Analyser → Planifier → Mobiliser → Exécuter → Vérifier → Optimiser → Apprendre`

- **Premier réflexe : l'auto-audit** : l'orchestrateur s'audite lui-même (dans l'exemple : 3 agents aux consignes obsolètes corrigés, 1 rappel mal calé recalé, 3 automatisations mortes supprimées avec accord).
- **3 mécanismes pour que ça dure** :
  1. **Mémoire d'erreurs** : `Cause + correction`, pour ne jamais répéter la même erreur.
  2. **Ce qui marche** : méthodes, préférences et décisions validées stockées en mémoire.
  3. **Bilan du vendredi** : **3 améliorations maximum** (pas 15).
- **Garde-fous (ce que ce n'est pas)** : pas d'IA consciente, pas d'action sans accord (rien de publié/acheté/envoyé sans validation). *Attention au piège signalé en commentaire (`@JuliannPod`) : si on valide trop de petites choses, on finit par tamponner en diagonale -> ne demander l'accord que sur les étapes engageantes.*

---

## 2. Système de mémoire & gouvernance d'agents de `@timseo_` (SEO KB)

Complément parfait pour notre tandem **Antigravity (Gemini 4) + Claude Code** :

1. **Mémoire transmissible (`raw/` + `wiki/`)** :
   - `raw/` : sources originales **en lecture seule** pour les agents (exports GSC, études, transcriptions, retours clients).
   - `wiki/` : fiches Markdown rédigées par l'agent, reliées entre elles, avec `wiki/index.md` et `wiki/log.md` daté + historique Git.
   - Chaque fiche renvoie à sa source, sa méthode, ses résultats et ses limites.
   - Objectif : n'importe quel nouveau modèle peut reprendre une mission avec la consigne : *« Reprends cette mission. Montre-moi la dernière décision validée, les données qui l'ont justifiée et ce qui peut avancer. »*
2. **Brancher les données métier réelles** :
   - Compléter les données publiques avec les vraies questions/objections clients (e-mails, support, appels) et les exports GSC dans `raw/data/exports-gsc/`.
3. **Méthodes & voix séparées des règles** :
   - `CLAUDE.md` charge `AGENTS.md` (règles projet).
   - Chaque `SKILL.md` décrit : déclencheur, fichiers à lire, outils à exécuter, livrable attendu.
   - Profil / règles / voix dans des fichiers dédiés (`about-me`, `my-rules`, `my-voice`).
4. **Handoff multi-modèles** :
   - Le même brief structuré doit pouvoir passer de Claude à Gemini/Codex avec les mêmes champs et les mêmes vérifications.
5. **Approbation sur version précise (empreinte)** :
   - Si un fichier déjà approuvé est modifié par l'agent, les livrables qui en dépendent repassent en revue.
6. **Traçabilité des constats** :
   - Distinguer explicitement dans chaque livrable : une **requête mesurée**, une **question observée (client/support)** et une **hypothèse**.
   - Relecture assistée (lien phrase ↔ source, pertinence des liens internes) ; ne passer en semi-automatique qu'après ≥ 80 % d'accord sur ≥ 30 verdicts humains.
7. **Boucle d'apprentissage & mesure J+30 / J+90** :
   - **Règle de la 2e occurrence** : à la deuxième fois qu'une correction revient, l'agent prépare une proposition de règle/skill/contrôle, **tranchée à la revue du vendredi**.
   - Relier chaque action publiée aux résultats mesurés à **J+30 et J+90**.

---

## 3. Ce qu'on applique concrètement dès maintenant à notre setup
1. Conserver notre structure `docs/antigravity-handoff/` comme **mémoire transmissible** commune entre Antigravity et Claude (en séparant les sources brutes et les fiches de décision).
2. Tenir un fichier **Mémoire d'erreurs & décisions** (`ERREURS_ET_DECISIONS.md` ou dans `HANDOFF.md`) + appliquer la **règle de la 2e occurrence** -> promotion dans `AGENTS.md`.
3. Instaurer un **Bilan du vendredi (max 3 améliorations)** sur ClipRoll + notre setup agent.
4. Systématiser la passe **Avocat du diable (`@verifier`)** sur les changements critiques (comme nous venons de le faire en vérifiant `localhost:8080` en vrai navigateur, ce qui a attrapé le serveur non redémarré et le bug CSS d'emoji).
