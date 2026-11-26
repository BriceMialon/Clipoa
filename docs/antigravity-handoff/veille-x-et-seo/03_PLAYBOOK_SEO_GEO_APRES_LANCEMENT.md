# Playbook SEO & GEO Complet — Phase 2 (dès mise en ligne de `cliproll.app`)

Sources analysées :
- `@hridoyreh` + commentaires (`https://x.com/hridoyreh/status/2125808766419419583`)
- `@asaio87` + commentaires (`https://x.com/asaio87/status/2125847840463233341`)
- `@alexgroberman` — Article X complet sur l'étude SE Ranking (`https://x.com/alexgroberman/status/2013257845714661480`)
- `@jakezward` ×2 + commentaires (`https://x.com/jakezward/status/2125280032662696172` & `2125228444531179554`)
- `@timseo_` — Infographie outils Google gratuits (`https://x.com/timseo_/status/2125631851427426532`)

---

## 1. Indexation IA & Moteurs — Checklist Jour 1 (`@hridoyreh` + commentaires)

À faire **le jour même de la mise en ligne** de `https://cliproll.app` (10–15 min) :

1. **Brave Search** : soumettre `https://cliproll.app` (avec `https://`) sur **`https://search.brave.com/submit-url`**.
   - *Pourquoi* : **Claude Web Search s'appuie sur Brave Search** — si ton site n'est pas dans Brave, Claude ne te cite tout simplement pas.
2. **Bing Webmaster Tools** (+ protocole **IndexNow**) : soumettre `cliproll.app` le même jour.
   - *Pourquoi* : **ChatGPT Search s'appuie sur Bing**, et IndexNow partage l'indexation avec toute l'alliance ouverte (Bing, Yandex, Seznam, Naver — hors Google).
3. **Google Search Console** : vérifier la propriété + soumettre `https://cliproll.app/sitemap.xml` + inspecter les URLs clés.
4. **ChatGPT Business Hub** : enregistrer ClipRoll sur **`https://chatgpt.com/business-hub`** (repéré en fil associé `@tonnoz`).
5. **Vérifier `robots.txt`** : s'assurer qu'aucune règle par défaut (hébergeur/CDN/Cloudflare) ne bloque **`OAI-SearchBot`**, **`PerplexityBot`**, **`ClaudeBot`**, **`GPTBot`** ou **`Google-Extended`**.

---

## 2. Comment apparaître dans Google AI Overviews, ChatGPT & Gemini (`@alexgroberman`)

Enseignements clés de l'étude **SE Ranking** (50 807 recherches, 465 823 citations) :
1. **Les AI Overviews explosent** (> 82 % sur les requêtes analysées) — la visibilité IA est devenue incontournable.
2. **Autorité + lisibilité machine > pedigree** : les IA infèrent la confiance via les signaux d'autorité de domaine (backlinks, mentions de marque, cohérence sémantique) + la facilité d'extraction du contenu.
3. **64 % des URLs citées par l'IA NE SONT PAS dans le Top 10 Google** (seulement 36 % dans le Top 10, 54 % Top 20, 74 % Top 100).
   - *Action* : ne pas viser uniquement le ranking de la homepage ; créer une **bibliothèque de pages citables** : comparatifs (`ClipRoll vs Crayo`, `ClipRoll vs ShortCrew`), pages FAQ structurées, définitions, guides d'achat, pages marque (`ClipRoll avis`, `ClipRoll tarifs BYOK`).
4. **YouTube est la source #1 citée dans les AI Overviews** (alors qu'il ne classe que 11e en organique !).
   - *Synergie directe pour ClipRoll* : publier des vidéos YouTube explicatives sur ClipRoll (démos, tutoriels « créer des Shorts en local », comparatifs) avec **transcriptions claires, chapitres Q&A et réponses directes** -> levier énorme pour se faire citer par Gemini / Google AI Overviews.
5. **Couverture à l'échelle** : une seule page bouge peu l'aiguille ; plusieurs dizaines de pages alignées et cohérentes construisent la confiance des LLMs. *« Construis une bibliothèque que l'IA peut citer, pas une brochure. »*

---

## 3. Les 20 Regex Google Search Console (`@jakezward`)

À utiliser dans **Google Search Console → Performances → Résultats de recherche → Nouveau filtre → Requête → Personnalisé (expression régulière)** dès que le site a des impressions :

### A. Requêtes longues & conversationnelles
- **4+ mots** : `^(?:\S+\s+){3,}\S+$`
- **8+ mots** : `^(?:\S+\s+){7,}\S+$`
- **10+ mots** : `^(?:\S+\s+){9,}\S+$`
- **Questions (EN)** : `^(who|what|when|where|why|how|which|can|could|should|would|will|do|does|did|is|are|was|were|has|have)\b`
- **Questions (FR adapté ClipRoll)** : `^(qui|quoi|quand|où|ou|pourquoi|comment|quel|quelle|quels|quelles|est-ce|peut-on|faut-il|combien)\b`
- **Style prompt IA** : `^(give me|show me|help me|explain|recommend|suggest|generate|summari[sz]e|create|list|compare|find me|tell me|donne|montre|explique|compare|meilleur)\b`

### B. Opportunités de contenu & questions
- **How-to / Tutoriels** : `\b(how to|how do i|guides?|tutorials?|tips|step by step|walkthroughs?|instructions?|getting started|learn how|comment|tuto|tutoriel|guide|étapes)\b`
- **Apprentissage / Explication** : `\b(learn|learning|help|explain|explainer|understand|beginner|basics|apprendre|débutant|comprendre|bases)\b`
- **Définitions** : `\b(what is|what are|define|definitions?|meanings?|means?|stands for|explained|c'est quoi|définition|signifie)\b`
- **FAQ** : `^(can|could|should|would|will|do|does|did|is|are|was|were|has|have|had|est-ce|peut|faut)\b`
- **Problèmes / Dépannage** : `\b(fix|fixing|errors?|issues?|problems?|not working|broken|troubleshoot(?:ing)?|repair|failed|erreur|problème|bug|ne marche pas|corriger)\b`

### C. Requêtes à forte intention d'achat (prioritaires pour ClipRoll)
- **Comparatifs** : `\b(vs|versus|compare|compared|comparing|comparisons?|alternatives?|competitors?|instead of|replacements?|better than|difference between|switch from|comparatif|meilleur que)\b`
- **Prix / Tarifs** : `\b(prices?|pricing|costs?|fees?|subscriptions?|how much|per month|per year|prix|tarif|coût|abonnement|gratuit|combien)\b`
- **Avis / Confiance** : `\b(reviews?|ratings?|reddit|trustpilot|g2|capterra|legit|scam|trustworthy|worth it|testimonials?|complaints?|avis|arnaque|fiable|test)\b`
- **Meilleur / Top** : `\b(best|top|better|cheapest|top[- ]rated|recommended|meilleur|meilleurs|top)\b`
- **Transactionnel** : `\b(buy|purchase|order|checkout|demo|sign up|free trial|sale|deal|discount|coupon|promo|affordable|budget|cheap|acheter|essai gratuit|code promo|télécharger)\b|\bunder\s+[$€£]?\d+`

### D. Opportunités niches & SaaS
- **Fraîcheur** : `\b(latest|new|newest|recent|updated|up to date|current|nouveau|mise à jour)\b|\b20\d{2}\b`
- **Support / Réputation** : `\b(customer service|support|refunds?|return policy|remboursement|support|garantie)\b`
- **Produit / Fonctionnalités** : `\b(features?|specs?|versions?|models?|quality|compatible|fonctionnalités|qualité|mac|windows)\b`
- **SaaS / Logiciels** : `\b(tools?|software|apps?|systems?|platforms?|applications?|programs?|solutions?|integrations?|api|outils?|logiciel|application)\b`
- **Local / Disponibilité** : `\b(near me|online|en ligne|local|hors ligne|offline)\b`

### Astuces clés des commentaires (`@jakezward`)
- **Quick Win pos 4–20 (`@BrianDreyer`)** : filtrer les questions où une page est déjà en **positions 4–20** avec beaucoup d'impressions et peu de clics -> **ajouter la question en H2 sur cette page existante et y répondre dans les 2 premières phrases** plutôt que d'écrire un nouvel article.
- **Limite connue (`@abhi100425`)** : le filtre par requête GSC masque les requêtes anonymisées (~40–45 % des clics sur certains sites) -> traiter ce résultat comme un **plancher**, pas comme l'exhaustivité.

---

## 4. Le Prompt SEO Condensé avec Export GSC (`@asaio87`)

Prompt exact à fournir à l'agent (avec l'export CSV de Google Search Console en pièce jointe) :

```text
You are an SEO writer. Write one article on [TOPIC] for [DOMAIN], using the attached GSC export to plan internal links.

INPUTS: topic, GSC data (query, page, clicks, impressions, CTR, position), product facts + prohibited claims, conversion page URL(s), brand voice/banned phrases, target country/language.

STEP 1 – READ THE GSC DATA BEFORE WRITING
- Normalize URLs (strip parameters). Ignore excluded locales, test/staging URLs, and branded queries.
- Cannibalization check: if an existing page already gets impressions for this topic's main queries, especially in positions 1-30, STOP and recommend a refresh of that page instead of a new article. Name the URL and its metrics.
- Pick internal link targets by topical relevance plus evidence:
  • Page-2 pages (avg position 11-30) on related queries. These get the most from extra links.
  • High-impression, low-CTR pages (>200 impressions, CTR <1%) on related intents.
  • Conversion/product pages always come first when relevant.
- Use 4-8 internal links. Each target must be a real URL from the data, never invented.
- Anchor text should come from the target page's actual ranking queries, phrased naturally. Don't use the same exact-match anchor twice, and don't link two pages that compete for the same intent.

STEP 2 – STRUCTURE
- Classify intent (how-to, listicle, comparison, use-case guide) and match the page type that ranks for it.
- TL;DR at the top. For a how-to, a 2-3 sentence summary. For a listicle, all items with links. For a comparison, a clear verdict on who should pick what.
- Right after the TL;DR, an answer-first block of 2-4 sentences that directly answers the main query.
- Intro of 2-3 short paragraphs max, with no scene-setting.
- How-to steps come before any background. Listicles name every tool early, and each tool gets a link, an honest drawback, and an image placeholder. Comparisons give the verdict early.
- Put the primary keyword in the H1 and in the first 100 words. Use question-style H2s where they match real GSC queries.
- End with a short, decision-oriented conclusion, then concise FAQs drawn from real queries in the data.

STEP 3 – VOICE
- Use simple words, short paragraphs, varied sentence rhythm, and specific numbers, examples, and tradeoffs.
- Banned words and phrases: "in today's fast-paced world", "let's dive in", unlock, harness, delve, seamless, robust, powerful, cutting-edge, game-changer, "it's important to note", "whether you're a..." (et leurs équivalents FR : "dans un monde en constante évolution", "plongeons dans", "révolutionnaire", "incontournable", "sans couture", "il est important de noter").
- Don't start sections the same way or use the same structure for every list item. No hedging unless the uncertainty is real, and no conclusion that just rephrases the intro.
- No em dashes unless the style guide allows them.

STEP 4 – FACT SAFETY
- Only use the product facts you were given. Never invent pricing, features, testimonials, reviews, benchmarks, or awards.
- Don't call something "free" when it's a free trial. Source competitor claims or soften them.
- If a needed fact is missing, flag it instead of guessing.

OUTPUT
1. Article (Markdown) with internal links inline.
2. Meta title (≤60 chars) and meta description (≤155 chars).
3. Internal link table: anchor | target URL | GSC evidence (query, position, impressions) | reason.
4. Asset/image queue and fact-check notes.
5. Self-QA: confirm TL;DR and answer-first block are present, intent matches, no invented facts, every link comes from the data, and no banned phrases. Fix anything that fails before returning.
```

*Bonus des commentaires* :
- Faire la QA finale manuellement ou via un **2e agent** chargé d'ajouter des avis/données terrain (`@asaio87`).
- Ajouter du **query fan-out** (sous-questions connexes posées aux LLMs) pour capter encore plus de trafic IA (`@Lucaungredda`).

---

## 5. Stack 100 % Outils Google Gratuits (`@timseo_`)

Remplacer les abonnements SEO coûteux par la suite gratuite Google + APIs :
- **Requêtes & veille** : Recherche Google, Google Trends, Keyword Planner (Google Ads), Google Alertes, Google Actualités, Gemini, YouTube Studio, Recherche YouTube.
- **Suivi & indexation** : Google Search Console, Inspection d'URL, Search Console Insights, Rapports IA de Search Console, Google Search Status Dashboard, outil de mise à jour de contenu obsolète.
- **Vitesse & audit technique** : PageSpeed Insights, Lighthouse, Lighthouse CI, Chrome DevTools, Chrome UX Report (CrUX), CrUX Vis, Google Safe Browsing.
- **Tests & balisage** : Test des résultats enrichis (JSON-LD), Outil d'aide au balisage, Data Highlighter, Analyseur `robots.txt` de Google.
- **Trafic & automatisation** : Google Analytics 4, Google Tag Manager, Looker Studio, Google Sheets, Apps Script, Google Colab, BigQuery Sandbox.
- **APIs gratuites pour nos agents** : Search Console API, Indexing API, PageSpeed Insights API, CrUX API, CrUX History API, Google Analytics Data API, YouTube Data API, YouTube Analytics API, Google Sheets API.
