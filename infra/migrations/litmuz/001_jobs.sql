-- Jobs: one row per verification submission.
-- Mutable status and progress: litmuz_app UPDATEs this table as a job advances.
-- Idempotent: safe to re-run.

BEGIN;

CREATE TABLE IF NOT EXISTS jobs (
  job_id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_sub     text NOT NULL,
  status       text NOT NULL DEFAULT 'queued'
                 CHECK (status IN ('queued', 'running', 'completed', 'failed')),
  stage        text,
  claims_total integer NOT NULL DEFAULT 0,
  claims_done  integer NOT NULL DEFAULT 0,
  error        text,
  report_id    uuid,
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS jobs_user_sub_created_at_idx ON jobs (user_sub, created_at DESC);
CREATE INDEX IF NOT EXISTS jobs_status_idx ON jobs (status);

COMMIT;
