-- Per-claim citation checks, evidence, and the append-only pipeline verdict.
-- verdicts is append-only: no UPDATE/DELETE is granted to any app role (005).
-- Idempotent: safe to re-run.

BEGIN;

CREATE TABLE IF NOT EXISTS cited_ids (
  id       bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  claim_id uuid NOT NULL REFERENCES claims (claim_id),
  id_type  text NOT NULL,
  id_value text NOT NULL
);
CREATE INDEX IF NOT EXISTS cited_ids_claim_idx ON cited_ids (claim_id);

CREATE TABLE IF NOT EXISTS citation_checks (
  id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  claim_id          uuid NOT NULL REFERENCES claims (claim_id),
  identifier        text NOT NULL,
  id_type           text NOT NULL,
  resolution_status text NOT NULL,
  source_status     text,
  title_match       text NOT NULL,
  author_match      text NOT NULL,
  year_match        text NOT NULL,
  resolver_path     text NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS citation_checks_claim_idx ON citation_checks (claim_id);

CREATE TABLE IF NOT EXISTS evidence (
  claim_id             uuid PRIMARY KEY REFERENCES claims (claim_id),
  evidence_sentence    text,
  source_locator       jsonb,
  evidence_not_located boolean NOT NULL DEFAULT false
);

CREATE TABLE IF NOT EXISTS verdicts (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  seq        bigint GENERATED ALWAYS AS IDENTITY,
  claim_id   uuid NOT NULL REFERENCES claims (claim_id),
  label      text NOT NULL,
  confidence numeric,
  rationale  text NOT NULL DEFAULT '',
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS verdicts_claim_idx ON verdicts (claim_id, seq);

COMMIT;
