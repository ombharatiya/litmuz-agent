"""One-shot bootstrap for the litmuz database.

Needs the admin (master) credentials once. Creates the database and the least-privilege
roles, applies the migrations as the admin (owner), runs an insert/select/reject smoke test
that proves append-only and least-privilege hold, and writes the generated role passwords to
a gitignored tfvars file. Secrets are never printed or logged.

Run from the repo:
  ADMIN_PGPASSWORD='<master password>' uv run python infra/migrations/litmuz/bootstrap.py

Optional env: ADMIN_PGHOST, ADMIN_PGPORT, ADMIN_PGUSER (default postgres),
ADMIN_PGDATABASE (default postgres), LITMUZ_DBNAME (default litmuz),
APP_PASSWORD / API_PASSWORD (generated when absent).
"""

from __future__ import annotations

import os
import pathlib
import secrets
import sys

import psycopg

from .provision import API_ROLE, APP_ROLE, provision

_DENIED = psycopg.errors.InsufficientPrivilege


def _default_tfvars_path() -> pathlib.Path:
    # packages/litmuz_store/src/litmuz_store/bootstrap.py -> repo root is parents[4].
    root = pathlib.Path(__file__).resolve().parents[4]
    return root / "infra" / "terraform" / "auth" / "terraform.tfvars"


def write_tfvars(path: pathlib.Path, values: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = [ln for ln in current.splitlines() if ln.strip()]
    for key, value in values.items():
        lines = [ln for ln in lines if not ln.strip().startswith(f"{key} ")]
        lines.append(f'{key} = "{value}"')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def smoke_test(admin_params: dict, dbname: str, app_password: str, api_password: str) -> None:
    """Verify the runtime roles behave as intended. Rolls back; leaves no rows."""
    app_params = {**admin_params, "dbname": dbname, "user": APP_ROLE, "password": app_password}
    with psycopg.connect(**app_params) as conn:
        conn.autocommit = False
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO jobs (user_sub, status) VALUES ('bootstrap-smoke', 'completed') "
                "RETURNING job_id"
            )
            job_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO reports (job_id, user_sub, memo_hash) "
                "VALUES (%s, 'bootstrap-smoke', 'smoke') RETURNING report_id",
                (job_id,),
            )
            report_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO claims (report_id, local_id, ordinal, text, source_span) "
                "VALUES (%s, 'c1', 0, 'smoke', '{\"start\":0,\"end\":5}') RETURNING claim_id",
                (report_id,),
            )
            claim_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO verdicts (claim_id, label) VALUES (%s, 'supported')", (claim_id,)
            )
            try:
                cur.execute("UPDATE verdicts SET rationale = 'x' WHERE claim_id = %s", (claim_id,))
            except _DENIED:
                pass
            else:
                raise SystemExit("smoke test failed: litmuz_app could UPDATE verdicts")
        conn.rollback()

    api_params = {**admin_params, "dbname": dbname, "user": API_ROLE, "password": api_password}
    with psycopg.connect(**api_params) as conn:
        conn.autocommit = False
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM jobs")
            cur.fetchone()
            try:
                cur.execute(
                    "INSERT INTO verdicts (claim_id, label) VALUES (gen_random_uuid(), 'supported')"
                )
            except _DENIED:
                pass
            else:
                raise SystemExit("smoke test failed: litmuz_api could INSERT a verdict")
        conn.rollback()


def main(tfvars_path: pathlib.Path | None = None) -> int:
    admin_password = os.environ.get("ADMIN_PGPASSWORD")
    if not admin_password:
        print("ADMIN_PGPASSWORD is required (the admin/master password).", file=sys.stderr)
        return 2

    admin_params = {
        "host": os.environ.get("ADMIN_PGHOST", "127.0.0.1"),
        "port": int(os.environ.get("ADMIN_PGPORT", "5432")),
        "user": os.environ.get("ADMIN_PGUSER", "postgres"),
        "password": admin_password,
        "dbname": os.environ.get("ADMIN_PGDATABASE", "postgres"),
    }
    dbname = os.environ.get("LITMUZ_DBNAME", "litmuz")
    app_password = os.environ.get("APP_PASSWORD") or secrets.token_hex(24)
    api_password = os.environ.get("API_PASSWORD") or secrets.token_hex(24)

    provision(admin_params, dbname=dbname, app_password=app_password, api_password=api_password)
    print(f"provisioned database '{dbname}' with roles {APP_ROLE} and {API_ROLE}")

    smoke_test(admin_params, dbname, app_password, api_password)
    print("smoke test OK: append-only and least-privilege verified")

    path = tfvars_path or _default_tfvars_path()
    write_tfvars(path, {"litmuz_app_password": app_password, "litmuz_api_password": api_password})
    print(f"wrote role passwords to {path} (gitignored)")
    print("bootstrap complete")
    return 0
