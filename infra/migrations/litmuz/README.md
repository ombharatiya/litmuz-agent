# infra/migrations/litmuz: database migrations

Hand-written, idempotent, numbered SQL migrations for the `litmuz` PostgreSQL database. They
are applied by `bootstrap.py` (in `packages/litmuz_store`), which creates the database and the
least-privilege application roles, runs the migrations, and executes an insert/select/reject
smoke test that proves the append-only provenance and least-privilege guarantees hold.

Append-only provenance is enforced at the database layer via `GRANT`s: the application role
can insert but not update or delete provenance rows.
