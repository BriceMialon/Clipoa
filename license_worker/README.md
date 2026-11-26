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
