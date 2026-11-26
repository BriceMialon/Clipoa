-- Base D1 du serveur de licence ClipRoll
CREATE TABLE IF NOT EXISTS licenses (
  key TEXT PRIMARY KEY,                -- CLIPOA-XXXX-XXXX-XXXX-XXXX
  customer_id TEXT NOT NULL UNIQUE,    -- Stripe cus_...
  subscription_id TEXT,                -- Stripe sub_...
  email TEXT,
  plan TEXT,                           -- monthly | yearly
  status TEXT NOT NULL DEFAULT 'incomplete', -- statut Stripe (trialing, active, past_due, canceled...)
  period_end INTEGER,                  -- fin de période payée (epoch s)
  created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS devices (
  key TEXT NOT NULL,
  device TEXT NOT NULL,                -- empreinte hachée envoyée par l'app
  name TEXT,
  last_seen INTEGER,
  PRIMARY KEY (key, device)
);
CREATE TABLE IF NOT EXISTS stripe_events (id TEXT PRIMARY KEY, at INTEGER);
