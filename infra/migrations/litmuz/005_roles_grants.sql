-- Least-privilege grants (AC-STORE-2, AC-STORE-4).
--
-- Assumes the login roles litmuz_app and litmuz_api already exist (created by the
-- bootstrap or the test harness) and that the tables are owned by a non-app role (the
-- migration runner). Because the app roles are not the table owner, they hold only the
-- privileges granted here, so UPDATE and DELETE on the append-only tables (verdicts,
-- reviewer_actions) are denied by Postgres itself, not by application code.
--
-- Idempotent: GRANT and REVOKE are safe to re-run.

BEGIN;

GRANT USAGE ON SCHEMA public TO litmuz_app, litmuz_api;

-- litmuz_app writes provenance. Jobs are the only mutable table (status and progress).
-- INSERT on verdicts and reviewer_actions is allowed (append); UPDATE and DELETE are not
-- granted, which makes those two tables append-only for the runtime.
GRANT SELECT, INSERT ON
  jobs, reports, claims, cited_ids, citation_checks, evidence, verdicts, reviewer_actions
  TO litmuz_app;
GRANT UPDATE ON jobs TO litmuz_app;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO litmuz_app;

-- litmuz_api reads everything and appends reviewer actions only. It has no INSERT on
-- verdicts or any other table, so a reviewer path can never forge a pipeline verdict.
GRANT SELECT ON ALL TABLES IN SCHEMA public TO litmuz_api;
GRANT INSERT ON reviewer_actions TO litmuz_api;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO litmuz_api;

COMMIT;
