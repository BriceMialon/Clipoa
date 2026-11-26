# ClipRoll : site public (cliproll.app)

HTML statique, une page par URL, à déployer tel quel (Cloudflare Pages ou GitHub Pages servent `tarifs.html` à l'adresse `/tarifs`).

| Fichier | URL |
|---|---|
| `index.html` | `/` (accueil, exemples, coûts, tarifs, FAQ) |
| `tarifs.html` | `/tarifs` (formules + FAQ abonnement) |
| `privacy.html` | `/privacy` (FR + EN ; l'EN sert à la vérification Google OAuth, ne pas retirer) |
| `terms.html` | `/terms` (conditions d'utilisation et de vente, FR + EN) |
| `404.html` | page introuvable (noindex) |
| `google42d62dcf06720b65.html` | vérification Google Search Console, ne pas supprimer |

## Avant la mise en ligne

1. **Boutons d'achat** : ils pointent vers `https://clipoa-license.clipoa-studio.workers.dev/checkout?plan=yearly|monthly` (redirection 303 du Worker vers Stripe Checkout). Si le Worker change d'adresse, remplacer cette URL dans `index.html` et `tarifs.html`. Côté Worker, mettre `SITE_URL = "https://cliproll.app"` (retour en cas d'abandon : `/tarifs`).
2. **Lien « Gérer mon abonnement »** : remplacer `https://billing.stripe.com/p/login/A_REMPLIR` (5 pages) par le lien de connexion du portail client Stripe (Dashboard Stripe, Réglages, Portail client, « Lien de connexion »).
3. **Vidéos d'exemple** : déposer `assets/exemples/exemple-1.mp4` + `exemple-1.jpg` (puis 2 et 3) et remplacer le texte de chaque bloc `.short-screen` par la balise `<video>` donnée en commentaire dans `index.html`.
4. **Conditions** : compléter les commentaires `À COMPLÉTER` / `À VALIDER` de `terms.html` (éditeur, SIRET, adresse, TVA, hébergeur, rétractation, médiateur).
5. Vérifier qu'aucune page ne contient plus `A_REMPLIR` : `grep -rl A_REMPLIR site_public`.
