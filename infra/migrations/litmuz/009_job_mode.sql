-- The verification criteria a job was submitted with: 'literature' (default; citations checked
-- against the primary literature) or 'genomic' (genomic claims checked against the Gladstone
-- HAR / Zoonomia reference). Stored on the job so the worker runs the right pipeline and the
-- studio can label a past session. Idempotent: safe to re-run.

BEGIN;

ALTER TABLE jobs ADD COLUMN IF NOT EXISTS mode text NOT NULL DEFAULT 'literature'
  CHECK (mode IN ('literature', 'genomic'));

COMMIT;
