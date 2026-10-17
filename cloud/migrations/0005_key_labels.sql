-- Dashboard v2: name API keys (device name for CLI logins) and carry the
-- device name through the device-code row to the minted key.
ALTER TABLE api_keys ADD COLUMN label TEXT;
ALTER TABLE device_codes ADD COLUMN device_name TEXT;
