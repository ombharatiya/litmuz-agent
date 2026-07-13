"""Root test fixtures. The PostgreSQL fixtures are lazy, so tests that do not request them
(the whole core suite) never touch a database. Integration tests that request app_conn /
api_conn / admin_conn get a freshly-truncated, provisioned litmuz_test database.
"""

import pytest

from litmuz_store.provision import API_ROLE, APP_ROLE
from litmuz_store.testing import connect, connect_admin, provision_test_db, truncate_all


@pytest.fixture(scope="session")
def provisioned() -> None:
    provision_test_db()


@pytest.fixture
def _clean_db(provisioned) -> None:
    truncate_all()


@pytest.fixture
def admin_conn(_clean_db):
    with connect_admin() as conn:
        yield conn


@pytest.fixture
def app_conn(_clean_db):
    with connect(APP_ROLE) as conn:
        yield conn


@pytest.fixture
def api_conn(_clean_db):
    with connect(API_ROLE) as conn:
        yield conn
