-- Reports and their claims. Write-once at job completion.
-- claim_id is a surrogate uuid (globally unique, the queue key); local_id keeps the
-- in-report ordinal id ("c1", "c2") for traceability.
-- Idempotent: safe to re-run.

BEGIN;

CREATE TABLE IF NOT EXISTS reports (
  report_id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id          uuid NOT NULL REFERENCES jobs (job_id),
  user_sub        text NOT NULL,
  memo_hash       text NOT NULL,
  model_versions  jsonb NOT NULL DEFAULT '{}'::jsonb,
  rubric_version  text NOT NULL DEFAULT '',
  summary_counts  jsonb NOT NULL DEFAULT '{}'::jsonb,
  unclaimed_spans jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS reports_user_sub_created_at_idx ON reports (user_sub, created_at DESC);

CREATE TABLE IF NOT EXISTS claims (
  claim_id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  report_id         uuid NOT NULL REFERENCES reports (report_id),
  local_id          text NOT NULL,
  ordinal           integer NOT NULL,
  text              text NOT NULL,
  source_span       jsonb NOT NULL,
  category          text,
  diagnostic        text,
  traffic_light     text,
  auto_pass_blocked boolean,
  auto_passed       boolean,
  routed_to_review  boolean,
  retrieval_mode    text,
  UNIQUE (report_id, local_id)
);

CREATE INDEX IF NOT EXISTS claims_report_ordinal_idx ON claims (report_id, ordinal);
CREATE INDEX IF NOT EXISTS claims_routed_idx ON claims (routed_to_review) WHERE routed_to_review;

COMMIT;
