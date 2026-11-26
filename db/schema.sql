-- ClipRoll Cloudflare D1 Schema (Privacy-by-Design — Zero PII / Zero Raw IP / Zero OAuth Tokens)
-- Database: clipoa-db
-- UUID: 3e9feaa3-ddd9-4f49-b3b2-110f390bc2d3
-- Region: WEUR (Western Europe)

CREATE TABLE IF NOT EXISTS licenses (
  license_key_hash TEXT PRIMARY KEY,
  plan TEXT NOT NULL DEFAULT 'pro',
  status TEXT NOT NULL DEFAULT 'active',
  max_devices INTEGER NOT NULL DEFAULT 2,
  customer_ref_hash TEXT DEFAULT '',
  expires_at TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS device_activations (
  license_key_hash TEXT NOT NULL,
  device_id_hash TEXT NOT NULL,
  app_version TEXT DEFAULT '',
  activated_at TEXT NOT NULL DEFAULT (datetime('now')),
  last_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (license_key_hash, device_id_hash),
  FOREIGN KEY (license_key_hash) REFERENCES licenses(license_key_hash) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_device_activations_license ON device_activations(license_key_hash);

CREATE TABLE IF NOT EXISTS app_releases (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  version TEXT NOT NULL,
  platform TEXT NOT NULL,
  download_url TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  release_notes TEXT DEFAULT '',
  is_latest INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (version, platform)
);

CREATE INDEX IF NOT EXISTS idx_app_releases_latest ON app_releases(platform, is_latest);
