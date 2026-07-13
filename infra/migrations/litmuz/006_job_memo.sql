-- The submitted memo is stored on the job so the worker can run it after the API returns.
-- Kept on jobs (not a separate table) because it is one-to-one with a submission and within
-- the input byte cap. Idempotent: safe to re-run.

BEGIN;

ALTER TABLE jobs ADD COLUMN IF NOT EXISTS memo text NOT NULL DEFAULT '';

COMMIT;
