"""Append-only and least-privilege enforced by Postgres GRANTs, not app code
(AC-STORE-2, AC-STORE-4). The rejections come from the database itself."""

import psycopg
import pytest

_DENIED = psycopg.errors.InsufficientPrivilege


def _seed(admin_conn) -> dict:
    """Insert one job -> report -> claim -> verdict -> reviewer_action chain, as owner."""
    with admin_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO jobs (user_sub, status) VALUES ('u1', 'completed') RETURNING job_id"
        )
        job_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO reports (job_id, user_sub, memo_hash) "
            "VALUES (%s, 'u1', 'h') RETURNING report_id",
            (job_id,),
        )
        report_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO claims (report_id, local_id, ordinal, text, source_span) "
            "VALUES (%s, 'c1', 0, 'a claim', '{\"start\":0,\"end\":7}') RETURNING claim_id",
            (report_id,),
        )
        claim_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO verdicts (claim_id, label, confidence) VALUES (%s, 'supported', 0.9)",
            (claim_id,),
        )
        cur.execute(
            "INSERT INTO reviewer_actions (claim_id, reviewer_identity, action) "
            "VALUES (%s, 'r', 'accept')",
            (claim_id,),
        )
    admin_conn.commit()
    return {"job_id": job_id, "report_id": report_id, "claim_id": claim_id}


# --- litmuz_app: writes provenance, jobs mutable, verdicts/reviewer_actions append-only ---


def test_app_can_insert_and_update_jobs(app_conn):
    with app_conn.cursor() as cur:
        cur.execute("INSERT INTO jobs (user_sub) VALUES ('u') RETURNING job_id")
        job_id = cur.fetchone()[0]
        cur.execute("UPDATE jobs SET status = 'running' WHERE job_id = %s", (job_id,))
    app_conn.commit()


def test_app_can_append_a_verdict(app_conn, admin_conn):
    ids = _seed(admin_conn)
    with app_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO verdicts (claim_id, label) VALUES (%s, 'contradicted')", (ids["claim_id"],)
        )
    app_conn.commit()


def test_app_cannot_update_verdicts(app_conn, admin_conn):
    ids = _seed(admin_conn)
    with pytest.raises(_DENIED), app_conn.cursor() as cur:
        cur.execute(
            "UPDATE verdicts SET rationale = 'tampered' WHERE claim_id = %s", (ids["claim_id"],)
        )
    app_conn.rollback()


def test_app_cannot_delete_verdicts(app_conn, admin_conn):
    ids = _seed(admin_conn)
    with pytest.raises(_DENIED), app_conn.cursor() as cur:
        cur.execute("DELETE FROM verdicts WHERE claim_id = %s", (ids["claim_id"],))
    app_conn.rollback()


def test_app_cannot_update_reviewer_actions(app_conn, admin_conn):
    _seed(admin_conn)
    with pytest.raises(_DENIED), app_conn.cursor() as cur:
        cur.execute("UPDATE reviewer_actions SET note = 'tampered'")
    app_conn.rollback()


def test_app_cannot_delete_reviewer_actions(app_conn, admin_conn):
    _seed(admin_conn)
    with pytest.raises(_DENIED), app_conn.cursor() as cur:
        cur.execute("DELETE FROM reviewer_actions")
    app_conn.rollback()


# --- litmuz_api: reads everything, appends reviewer actions only ---


def test_api_can_select_all(api_conn, admin_conn):
    _seed(admin_conn)
    with api_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM reports")
        assert cur.fetchone()[0] == 1
        cur.execute("SELECT count(*) FROM verdicts")
        assert cur.fetchone()[0] == 1


def test_api_can_append_a_reviewer_action(api_conn, admin_conn):
    ids = _seed(admin_conn)
    with api_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO reviewer_actions (claim_id, reviewer_identity, action) "
            "VALUES (%s, 'rev', 'add_note')",
            (ids["claim_id"],),
        )
    api_conn.commit()


def test_api_cannot_insert_a_verdict(api_conn, admin_conn):
    ids = _seed(admin_conn)
    with pytest.raises(_DENIED), api_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO verdicts (claim_id, label) VALUES (%s, 'supported')", (ids["claim_id"],)
        )
    api_conn.rollback()


def test_api_cannot_insert_a_report(api_conn, admin_conn):
    ids = _seed(admin_conn)
    with pytest.raises(_DENIED), api_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO reports (job_id, user_sub, memo_hash) VALUES (%s, 'u', 'h')",
            (ids["job_id"],),
        )
    api_conn.rollback()
