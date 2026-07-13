"""Migrations apply idempotently against a real Postgres (AC-STORE-3)."""

from litmuz_store.migrations import apply_migrations, migration_files


def test_all_migrations_are_present_and_ordered():
    names = [p.name for p in migration_files()]
    assert names == [
        "001_jobs.sql",
        "002_reports_claims.sql",
        "003_citations_evidence_verdicts.sql",
        "004_reviewer_actions.sql",
        "005_roles_grants.sql",
        "006_job_memo.sql",
        "007_job_title.sql",
    ]


def test_migrations_are_idempotent(admin_conn):
    # The session fixture already applied them once; a second application is a clean no-op.
    apply_migrations(admin_conn)
    apply_migrations(admin_conn)
    with admin_conn.cursor() as cur:
        for table in ("jobs", "reports", "claims", "verdicts", "reviewer_actions"):
            cur.execute("SELECT to_regclass(%s)", (f"public.{table}",))
            assert cur.fetchone()[0] is not None, f"{table} missing after migrations"
