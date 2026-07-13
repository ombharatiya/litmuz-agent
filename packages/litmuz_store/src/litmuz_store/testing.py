"""Reusable PostgreSQL test harness, shared by the store and service integration tests.

Connection params come from the environment (PGHOST, PGPORT, PGUSER, PGPASSWORD) with
defaults for a local docker postgres:17.
"""

from __future__ import annotations

import os

import psycopg

from .provision import API_ROLE, APP_ROLE, provision

TEST_DB = "litmuz_test"
APP_PW = "app_pw_test"
API_PW = "api_pw_test"

_ALL_TABLES = (
    "reviewer_actions, verdicts, evidence, citation_checks, cited_ids, claims, reports, jobs"
)


def admin_params(dbname: str = "postgres") -> dict:
    return {
        "host": os.environ.get("PGHOST", "127.0.0.1"),
        "port": int(os.environ.get("PGPORT", "5432")),
        "user": os.environ.get("PGUSER", "postgres"),
        "password": os.environ.get("PGPASSWORD", "postgres"),
        "dbname": dbname,
    }


def provision_test_db() -> None:
    with psycopg.connect(autocommit=True, **admin_params()) as conn, conn.cursor() as cur:
        cur.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')
    provision(admin_params(), dbname=TEST_DB, app_password=APP_PW, api_password=API_PW)


def truncate_all() -> None:
    with psycopg.connect(autocommit=True, **admin_params(TEST_DB)) as conn, conn.cursor() as cur:
        cur.execute(f"TRUNCATE {_ALL_TABLES} RESTART IDENTITY CASCADE")


def connect(role: str) -> psycopg.Connection:
    password = {APP_ROLE: APP_PW, API_ROLE: API_PW}[role]
    return psycopg.connect(**{**admin_params(TEST_DB), "user": role, "password": password})


def connect_admin() -> psycopg.Connection:
    return psycopg.connect(**admin_params(TEST_DB))
