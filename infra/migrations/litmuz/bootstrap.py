#!/usr/bin/env python
"""Thin CLI entry point for the litmuz database bootstrap.

The logic lives in litmuz_store.bootstrap so it can be tested. Run from the repo:
  ADMIN_PGPASSWORD='<master password>' uv run python infra/migrations/litmuz/bootstrap.py
"""

from litmuz_store.bootstrap import main

if __name__ == "__main__":
    raise SystemExit(main())
