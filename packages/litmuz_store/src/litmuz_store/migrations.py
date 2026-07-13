"""Apply the hand-written SQL migrations in order (AC-STORE-3).

No ORM and no auto-migrate. Each file is idempotent, so applying the set twice is a clean
no-op. The migrations live in the repo at infra/migrations/litmuz.
"""

from __future__ import annotations

import pathlib


def _migrations_dir() -> pathlib.Path:
    """Locate infra/migrations/litmuz by walking up from this file.

    Resolved lazily and defensively: in the source tree the repo root is four levels up,
    but in a container image the package may sit at a shallow path (site-packages copied to
    the Lambda task root), where a fixed parents[4] raises IndexError at import time. The
    adapters import this package without ever applying migrations, so import must not
    depend on the install layout.
    """
    here = pathlib.Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "infra" / "migrations" / "litmuz"
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError(
        "infra/migrations/litmuz not found relative to litmuz_store; migrations can only "
        "be applied from a source checkout (bootstrap and tests), not from an installed image"
    )


def migration_files() -> list[pathlib.Path]:
    """The numbered .sql migrations, in lexical (numeric) order."""
    return sorted(_migrations_dir().glob("[0-9][0-9][0-9]_*.sql"))


def apply_migrations(conn) -> list[str]:
    """Execute every migration on the connection. Returns the file names applied."""
    applied: list[str] = []
    for path in migration_files():
        sql = path.read_text(encoding="utf-8")
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
        applied.append(path.name)
    return applied
