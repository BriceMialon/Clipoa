# AGENTS.md — Règles communes Claude ↔ Antigravity (ClipRoll)

Brice code avec **deux agents qui se relaient** : Claude et Antigravity. Quand l'un n'a plus de tokens, l'autre reprend. **Les deux peuvent modifier n'importe quelle partie de l'app** : pas de zone réservée. Ces règles servent à ce que le relais se fasse sans perte ni conflit.

Pour la carte du code, les chemins, les tests et le redémarrage : lire **`CLAUDE.md`** (valable pour les deux agents).

## Avant de commencer
1. `git checkout main && git pull` : toujours partir du `main` à jour.
2. Lire **`docs/HANDOFF.md`** : ce que l'autre agent a laissé en cours.
3. Regarder les **PR ouvertes** (GitHub `BriceMialon/Clipoa`). Si une PR de l'autre agent touche les mêmes fichiers : la fusionner d'abord (si elle est prête et que Brice l'a validée), sinon partir de sa branche ou demander à Brice.

## Pendant le travail
- **Une branche et une petite PR par sujet** : `claude/<sujet>` ou `gemini/<sujet>`.
- **Commiter souvent** (à chaque étape qui marche), jamais un gros lot non commité. Pousser à chaque commit.
- Lancer les tests du module touché avant chaque commit (`./venv/bin/python -m unittest tests.test_<module>`).
- **Fusion rapide** : une PR ne doit pas traîner plus d'une journée. Plus elle vit longtemps, plus les conflits grossissent.
- **Un seul serveur sur le port 8080.** Avant d'en lancer un, couper l'ancien (`lsof -ti :8080 | xargs kill -9`), quel que soit l'agent qui l'a lancé.
- `storage/` n'est pas dans Git : un worktree séparé n'a ni clés API ni comptes. Tester ce qui en a besoin depuis le dossier principal, ne jamais copier ni écraser `storage/settings.json` ou `storage/social_accounts.json`.

## Avant de s'arrêter (tokens bientôt épuisés, fin de session)
1. Tout commiter et pousser, même un travail inachevé (préfixe `WIP:` dans le message).
2. Ouvrir ou mettre à jour la PR (en brouillon si inachevée).
3. Mettre à jour **`docs/HANDOFF.md`** : en cours, branche/PR, fichiers touchés, prochaine étape. C'est le seul journal partagé (remplace `docs/antigravity-handoff/SYNC_CLAUDE.md`).

## Décisions réservées à Brice
Ne jamais changer sans son accord explicite : **prix et offre** (19 €/mois, 149 €/an, essai, limites), nom/marque, identifiants techniques déployés (`clipoa-oauth`, `clipoa-license`, callbacks OAuth, `~/Library/Clipoa`), choix de distribution, suppression d'une fonction existante. Proposer, puis attendre sa réponse.
