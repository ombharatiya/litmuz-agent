-- A short, human-readable title for a job, generated from the memo by a small model so each
-- session is identifiable in the studio list. Falls back to a memo snippet when empty.
-- Idempotent: safe to re-run.

BEGIN;

ALTER TABLE jobs ADD COLUMN IF NOT EXISTS title text NOT NULL DEFAULT '';

COMMIT;
