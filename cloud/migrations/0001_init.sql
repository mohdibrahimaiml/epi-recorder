-- EPI Cloud D1 schema, M0. Witness entries live in each inbox's Durable
-- Object SQLite, not here.
-- M0 addition vs plan §3: `rate_counters` backs the §6.1 rate limits
-- (login 10/min/IP, witness 600/min/inbox, push 60/min/key) on Workers,
-- which have no shared in-memory state across isolates.

CREATE TABLE orgs (id TEXT PRIMARY KEY, slug TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
  plan TEXT NOT NULL DEFAULT 'free', created_at TEXT NOT NULL);
CREATE TABLE users (id TEXT PRIMARY KEY, email TEXT, display_name TEXT, created_at TEXT NOT NULL);
CREATE TABLE identities (provider TEXT NOT NULL CHECK (provider IN ('github','google')),
  provider_user_id TEXT NOT NULL, user_id TEXT NOT NULL REFERENCES users(id),
  PRIMARY KEY (provider, provider_user_id));
CREATE TABLE memberships (org_id TEXT NOT NULL, user_id TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('owner','member','viewer')), PRIMARY KEY (org_id, user_id));
CREATE TABLE invites (id TEXT PRIMARY KEY, org_id TEXT NOT NULL, email TEXT NOT NULL, role TEXT NOT NULL,
  token_hash TEXT UNIQUE NOT NULL, expires_at TEXT NOT NULL, accepted_at TEXT);
CREATE TABLE sessions (id_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL, expires_at TEXT NOT NULL);
CREATE TABLE api_keys (id TEXT PRIMARY KEY, org_id TEXT NOT NULL, prefix TEXT NOT NULL,
  key_hash TEXT UNIQUE NOT NULL, scopes TEXT NOT NULL, created_by TEXT NOT NULL,
  created_at TEXT NOT NULL, last_used_at TEXT, revoked_at TEXT);
CREATE TABLE agents (id TEXT PRIMARY KEY, org_id TEXT NOT NULL, name TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL, UNIQUE (org_id, name));
CREATE TABLE inboxes (id TEXT PRIMARY KEY, org_id TEXT NOT NULL, customer_label TEXT NOT NULL,
  hmac_secret_enc TEXT NOT NULL, created_at TEXT NOT NULL, closed_at TEXT);
CREATE TABLE checkpoints (inbox_id TEXT NOT NULL, day TEXT NOT NULL, count INTEGER NOT NULL,
  head_hash TEXT NOT NULL, signature TEXT NOT NULL, signed_at TEXT NOT NULL,
  rekor_uuid TEXT, rekor_log_index INTEGER, tsa_token_b64 TEXT, PRIMARY KEY (inbox_id, day));
CREATE TABLE artifacts (
  id TEXT PRIMARY KEY, org_id TEXT NOT NULL, agent_id TEXT,
  claimed_sha256 TEXT NOT NULL,
  claimed_crc32 INTEGER NOT NULL,
  size_bytes INTEGER NOT NULL, manifest_json TEXT NOT NULL,
  spec_version TEXT, workflow_id TEXT, goal TEXT, steps INTEGER, sealed_at TEXT,
  key_fingerprint TEXT, signature_check TEXT NOT NULL,
  witness_status TEXT NOT NULL,
  reason TEXT,
  object_key TEXT NOT NULL, upload_state TEXT NOT NULL DEFAULT 'pending',
  uploaded_at TEXT NOT NULL, retention_until TEXT NOT NULL, legal_hold INTEGER NOT NULL DEFAULT 0,
  deleted_at TEXT, UNIQUE (org_id, claimed_sha256));
CREATE INDEX artifacts_org_time ON artifacts(org_id, uploaded_at DESC);
CREATE TABLE org_keys (id TEXT PRIMARY KEY, org_id TEXT NOT NULL, public_key TEXT NOT NULL,
  fingerprint TEXT NOT NULL, label TEXT, valid_from TEXT NOT NULL, revoked_at TEXT, revoke_reason TEXT,
  UNIQUE (org_id, public_key));
CREATE TABLE share_links (id TEXT PRIMARY KEY, org_id TEXT NOT NULL, token_hash TEXT UNIQUE NOT NULL,
  label TEXT NOT NULL, scope TEXT NOT NULL, created_at TEXT NOT NULL, expires_at TEXT NOT NULL,
  revoked_at TEXT);
CREATE TABLE trust_events (id INTEGER PRIMARY KEY AUTOINCREMENT, share_link_id TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('opened','verified_file','downloaded_pack','downloaded_witness')),
  detail TEXT, at TEXT NOT NULL);
CREATE TABLE storage_targets (org_id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK (kind IN ('s3','r2')),
  endpoint TEXT NOT NULL, bucket TEXT NOT NULL, region TEXT, prefix TEXT,
  last_check_at TEXT, last_check_ok INTEGER);
CREATE TABLE audit_log (seq INTEGER PRIMARY KEY AUTOINCREMENT, org_id TEXT, actor TEXT NOT NULL,
  action TEXT NOT NULL, detail TEXT NOT NULL, at TEXT NOT NULL, prev_hash TEXT NOT NULL, entry_hash TEXT NOT NULL);
CREATE TABLE rate_counters (key TEXT PRIMARY KEY, count INTEGER NOT NULL, window_expires_at TEXT NOT NULL);
