-- One report per job. Before the stale-running reclaim in claim_job, only one worker could
-- ever run a job (a 'running' row was never reclaimed), so this invariant held implicitly.
-- The reclaim can now transiently overlap a still-live worker, so enforce it at the database:
-- persist_report's ON CONFLICT (job_id) makes the second write a no-op instead of a duplicate
-- report (AC-JOB-5).
-- Idempotent: safe to re-run.

BEGIN;

CREATE UNIQUE INDEX IF NOT EXISTS reports_job_id_key ON reports (job_id);

COMMIT;
