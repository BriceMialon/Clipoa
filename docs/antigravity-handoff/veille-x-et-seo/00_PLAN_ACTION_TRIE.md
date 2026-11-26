# Plan d'Action Trié — Veille X, Setup Agent, ClipRoll & SEO/GEO

Date : 2026-11-26  
Dossier complet partagé (Antigravity + Claude) : `docs/antigravity-handoff/veille-x-et-seo/`

Ce dossier centralise l'intégralité des 8 sources X analysées (`@profpicsou` + vidéo 1m20, `@jeffar_ai` thread complet 8 prompts, `@hridoyreh` + commentaires, `@asaio87` + commentaires, `@alexgroberman` article complet, `@jakezward` ×2 + commentaires, `@timseo_` ×2 infographies) et les trie en **2 phases opérationnelles**.

---

## PHASE 1 — À FAIRE DÈS MAINTENANT (avant la mise en ligne du site)

### 1. Améliorer notre setup d'agents (Antigravity + Claude)
*Source : [01_SETUP_AGENT_JARVIS_ET_KB.md](./01_SETUP_AGENT_JARVIS_ET_KB.md) (`@profpicsou` + `@timseo_`)*
- **Mémoire transmissible `raw/` + `wiki/`** : garder les exports/sources brutes en lecture seule dans `raw/` et les décisions/fiches datées dans `wiki/` (`index.md` + `log.md`) pour que n'importe quel modèle (Claude ou Gemini) puisse reprendre un dossier sans repartir de zéro.
- **Auto-audit périodique** : lancer un audit des consignes/skills/règles obsolètes et supprimer les scripts/automatisations morts.
- **Mémoire d'erreurs + règle de la 2e occurrence** : noter chaque erreur (cause + correction) ; dès qu'une même erreur ou correction revient une **2e fois**, proposer une nouvelle règle dans `AGENTS.md` / skill.
- **Bilan du vendredi (max 3 améliorations)** : un rendez-vous hebdomadaire court avec **3 améliorations maximum** (pas 15), validées par l'humain.
- **Rôle « Avocat du diable » (`@tamila` / `@verifier`)** : systématiser la passe adversariale avant toute grosse décision produit/marketing ou modification critique.
- **Garde-fou humain strict** : rien n'est publié, acheté, déployé ou envoyé sans accord explicite.

### 2. Muscler l'outil d'analyse & de création de ClipRoll
*Source : [02_OUTIL_ANALYSE_CLIPROLL_JEFFAR.md](./02_OUTIL_ANALYSE_CLIPROLL_JEFFAR.md) (`@jeffar_ai` — 8 prompts)*
- **Enrichir l'onglet Statistiques (`core/channel_stats.py`)** avec le **Prompt #1 (Channel Audit System)** : au lieu de seulement noter chaque vidéo isolément, générer un **audit global de la chaîne** sur les 12 derniers Shorts (scorecard par pilier : hook visuel, rythme B-roll/captions, durée, engagement, les 3 plus grosses fuites de rétention, une formule d'accroche réécrite et un plan d'action priorisé).
- **Intégrer les Prompts #2 à #8 dans le pipeline de script/montage ClipRoll** :
  - **1.5s Hook Rewrite** (*Evidence + Betrayal*, caption gravée 4 mots max, ouverture parlée < 7 mots, preuve visuelle frame 1).
  - **Script Pruner** (zéro intro polie, phrases < 8 mots, payoff avant la 20e seconde, ~130 mots pour 30 s).
  - **Pattern Interrupt toutes les 6 s** (zoom punch / shake / pop graphique + SFX swoosh/pop/bass drop).
  - **Seamless Loop & Comment Trigger** (question binaire polarisante à réponse 1 mot + boucle grammaticale sans pause vers le hook d'ouverture pour dépasser 100 % de watch time).
  - **Pre-Upload Swipe-Away Audit** (repérer la seconde exacte où le viewer risque de swiper avant l'export + checklist 5 points).

### 3. Préparer la page `cliproll.app` avant déploiement (pré-requis SEO/GEO)
*Sources : `@hridoyreh`, `@alexgroberman`, `@asaio87`*
- **Vérifier `landing/robots.txt`** pour autoriser explicitement les crawlers IA (`OAI-SearchBot`, `PerplexityBot`, `ClaudeBot`, `GPTBot`) — ne surtout pas les bloquer par défaut.
- **Prévoir la structure "bibliothèque citable" dès la V1** : en plus de la landing, préparer 3–5 pages à forte intention commerciale/citable (ex : `ClipRoll vs Crayo`, `ClipRoll vs ShortCrew`, `Créer des YouTube Shorts sans abonnement à crédits (BYOK)`, `FAQ ClipRoll`) avec blocs **TL;DR + Answer-First (2–4 phrases)** sous des H2 formulés en questions.
- **Prévoir des vidéos YouTube officielles ClipRoll avec transcriptions propres** : YouTube est la **source #1 citée par Google AI Overviews** (même quand la vidéo est 11e en organique !).

---

## PHASE 2 — DÈS QUE `cliproll.app` EST EN LIGNE (Playbook SEO / GEO)

*Détail complet prêt à exécuter dans [03_PLAYBOOK_SEO_GEO_APRES_LANCEMENT.md](./03_PLAYBOOK_SEO_GEO_APRES_LANCEMENT.md).*

### Jour 1 de la mise en ligne (15 minutes)
1. **Google Search Console** : soumettre `https://cliproll.app/sitemap.xml` + inspecter la homepage.
2. **Brave Search** : soumettre `https://cliproll.app` sur `https://search.brave.com/submit-url` (**critique : Claude Web Search s'appuie sur Brave** — sans ça, Claude ne cite pas le site).
3. **Bing Webmaster Tools** (+ IndexNow) : soumettre le site le même jour (**critique : ChatGPT Search s'appuie sur Bing**).
4. **ChatGPT Business Hub** : enregistrer le SaaS sur `https://chatgpt.com/business-hub`.
5. **Stack Google 100 % gratuite (`@timseo_`)** : brancher GA4, vérifier PageSpeed Insights / Lighthouse / Rich Results Test (JSON-LD `SoftwareApplication` + `FAQPage`), et vérifier `robots.txt`.

### Semaines 2–4+ (dès les premières impressions dans GSC)
1. **Extraction des requêtes cachées (`@jakezward`)** : appliquer les **20 filtres regex GSC** (en priorité : questions `^(who|what|...|comment|pourquoi|quel|est-ce)...`, comparatifs `vs|alternative|avis`, pricing).
2. **Quick Wins positions 4–20** : pour chaque question à fortes impressions / faibles clics sur une page déjà positionnée 4–20, **ajouter la question en H2 et y répondre dans les 2 premières phrases** (plutôt que de créer un nouvel article qui cannibalise).
3. **Production d'articles SEO/GEO pilotés par export GSC (`@asaio87`)** : utiliser le **prompt SEO condensé complet** (anti-cannibalisation pos 1–30, maillage interne 4–8 liens vers pages pos 11–30 et pages >200 imp / CTR <1%, structure TL;DR + Answer-First, zéro vocabulaire IA banni, fact-checking strict, Self-QA + query fan-out LLM).
4. **Suivi J+30 et J+90 (`@timseo_`)** : logguer chaque intervention SEO (point de départ, action réelle, résultat J+30/J+90) dans la base de connaissances du projet.
