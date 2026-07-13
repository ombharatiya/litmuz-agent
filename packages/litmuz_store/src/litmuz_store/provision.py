"""Create the database and least-privilege roles, then apply the migrations.

Shared by the bootstrap CLI and the integration-test harness so both provision an identical
schema. The migration runner (the admin connection) owns the tables, so litmuz_app and
litmuz_api hold only the privileges granted in 005, which is what makes the append-only
tables append-only (AC-STORE-2, AC-STORE-4).
"""

from __future__ import annotations

import psycopg
from psycopg import sql

from .migrations import apply_migrations

APP_ROLE = "litmuz_app"
API_ROLE = "litmuz_api"


def _role_exists(cur, name: str) -> bool:
    cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (name,))
    return cur.fetchone() is not None


def _database_exists(cur, name: str) -> bool:
    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,))
    return cur.fetchone() is not None


def _ensure_role(cur, name: str, password: str) -> None:
    # DDL utility statements (CREATE/ALTER ROLE) cannot take bound parameters, so the
    # password is composed as a safely-quoted literal with psycopg.sql.
    verb = "ALTER" if _role_exists(cur, name) else "CREATE"
    cur.execute(
        sql.SQL("{verb} ROLE {role} WITH LOGIN PASSWORD {pw}").format(
            verb=sql.SQL(verb),
            role=sql.Identifier(name),
            pw=sql.Literal(password),
        )
    )


def provision(
    admin_params: dict,
    *,
    dbname: str = "litmuz",
    app_password: str,
    api_password: str,
) -> None:
    """Idempotently create roles and the database, then apply the migrations.

    ``admin_params`` are psycopg connection kwargs for a superuser (or a role that can create
    roles and databases), pointing at an existing maintenance database (for example postgres).
    """
    with psycopg.connect(autocommit=True, **admin_params) as conn, conn.cursor() as cur:
        _ensure_role(cur, APP_ROLE, app_password)
        _ensure_role(cur, API_ROLE, api_password)
        if not _database_exists(cur, dbname):
            cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(dbname)))

    target_params = {**admin_params, "dbname": dbname}
    with psycopg.connect(**target_params) as conn:
        apply_migrations(conn)
