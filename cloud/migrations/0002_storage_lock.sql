-- M4: vendor-reported Object Lock state for the trust page.
-- (storage_targets itself shipped in 0001_init.sql.)
ALTER TABLE storage_targets ADD COLUMN object_lock TEXT NOT NULL DEFAULT 'unknown';
