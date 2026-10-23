-- Device login with customer binding (onboarding simplification).
-- The browser asks which customer the computer records for at authorize
-- time; the witness URL + sealed secret travel back to the CLI with the
-- push key (single retrieval, like api_key_raw).
ALTER TABLE device_codes ADD COLUMN customer_label TEXT;
ALTER TABLE device_codes ADD COLUMN witness_url TEXT;
ALTER TABLE device_codes ADD COLUMN witness_secret_enc TEXT;
