-- Login cleanup: safe account linking + device flow for `epi cloud login`.
-- 1) Track verified email so cross-provider linking requires BOTH sides verified.
ALTER TABLE users ADD COLUMN email_verified INTEGER NOT NULL DEFAULT 0;

-- Backfill: existing rows predate verification tracking. Treat rows that
-- already own a Google identity as verified (Google only returns verified
-- semantics via email_verified=true at link time going forward; historical
-- Google-linked emails were verified at sign-in), leave GitHub-only rows
-- unverified (0) so a later verified Google login creates a separate
-- account instead of joining an attacker's pre-registered row.
-- This runs once; new sign-ins set the flag explicitly.
UPDATE users SET email_verified = 1 WHERE id IN (
  SELECT user_id FROM identities WHERE provider = 'google'
);

-- 2) Device-code flow: `epi cloud login` (no flags) polls for a push-only key.
CREATE TABLE device_codes (
  code TEXT PRIMARY KEY,
  status TEXT NOT NULL CHECK (status IN ('pending','authorized')) DEFAULT 'pending',
  org_id TEXT,
  api_key_id TEXT,
  api_key_raw TEXT,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  authorized_at TEXT
);
