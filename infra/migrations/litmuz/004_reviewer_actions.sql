-- Reviewer actions: the append-only human-review audit log.
-- effective_verdict is a projection over this table (latest action wins), never a mutable
-- column. litmuz_api may INSERT here; no role is granted UPDATE/DELETE (005).
-- Idempotent: safe to re-run.

BEGIN;

CREATE TABLE IF NOT EXISTS reviewer_actions (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  seq               bigint GENERATED ALWAYS AS IDENTITY,
  claim_id          uuid NOT NULL REFERENCES claims (claim_id),
  reviewer_identity text NOT NULL,
  action            text NOT NULL
                      CHECK (action IN ('accept', 'override_verdict', 'add_note')),
  prior_verdict     jsonb,
  new_verdict       jsonb,
  note              text NOT NULL DEFAULT '',
  created_at        timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS reviewer_actions_claim_idx ON reviewer_actions (claim_id, seq);

COMMIT;
