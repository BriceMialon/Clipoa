# clipoa-license (Cloudflare Worker)

Serveur d'abonnement et de licence de Clipoa. Détail : `docs/HISTORIQUE.md`, section « Abonnement Stripe et licence ».

Mise en place (mode test Stripe) :
1. `cp wrangler.toml.example wrangler.toml`, puis `npx wrangler d1 create clipoa-license` et coller l'id.
2. `npx wrangler d1 execute clipoa-license --remote --file=schema.sql`
3. Stripe (mode test) : créer le produit Clipoa et ses prix mensuel et annuel → `PRICE_MONTHLY` / `PRICE_YEARLY`.
4. `python3 gen_keys.py` → `npx wrangler secret put LICENSE_SIGNING_KEY` ; clé publique dans `core/license.py` (`DEFAULT_PUBKEY_HEX`).
5. `npx wrangler secret put STRIPE_SECRET_KEY` (sk_test_...), `npx wrangler deploy`.
6. Stripe → Webhooks → `https://<worker>/stripe/webhook`, événements `checkout.session.completed` et `customer.subscription.*` → `npx wrangler secret put STRIPE_WEBHOOK_SECRET`.
7. Stripe → Portail client : activer résiliation et changement de carte.
8. Anti-churn (portail, sans code) : Portail client → Résiliation → activer « Demander la raison » et « Offre de fidélisation » (coupon, ex. -50 % sur 1 mois). Mettre l'abonnement en pause n'est pas proposé par le portail : à ajouter dans le Worker si on le veut.

Prix décidés (26/11/2026) : 19 €/mois et 149 €/an (annuel présélectionné), essai 3 jours carte demandée.
