-- Customer-facing key list: which customer a computer records for.
ALTER TABLE api_keys ADD COLUMN customer_label TEXT;
-- Re-login on the same computer: hash of the key it already holds, revoked
-- when the new key is authorized (the CLI proves possession by sending it).
ALTER TABLE device_codes ADD COLUMN replaces_key_hash TEXT;
