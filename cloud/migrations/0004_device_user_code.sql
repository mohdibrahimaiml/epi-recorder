-- RFC 8628 device flow: short user code typed by the user (the long
-- device secret never appears in a URL), plus key-hygiene cleanup.
-- user_code is the 9-char "XXXX-XXXX" string shown in the terminal;
-- code (device secret) stays server-side + in the CLI only.
ALTER TABLE device_codes ADD COLUMN user_code TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS idx_device_codes_user_code ON device_codes(user_code);
