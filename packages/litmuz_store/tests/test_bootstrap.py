"""The bootstrap provisions, runs the smoke test, and writes passwords to a gitignored
tfvars file, never to logs (Phase 3 scenario). Uses the same role passwords as the harness
so the shared cluster roles are left unchanged."""

from litmuz_store import bootstrap

# Must match conftest APP_PW / API_PW so the shared roles keep the harness passwords.
_APP_PW = "app_pw_test"
_API_PW = "api_pw_test"


def _set_admin_env(monkeypatch) -> None:
    monkeypatch.setenv("ADMIN_PGHOST", "127.0.0.1")
    monkeypatch.setenv("ADMIN_PGPORT", "5432")
    monkeypatch.setenv("ADMIN_PGUSER", "postgres")
    monkeypatch.setenv("ADMIN_PGPASSWORD", "postgres")
    monkeypatch.setenv("ADMIN_PGDATABASE", "postgres")
    monkeypatch.setenv("LITMUZ_DBNAME", "litmuz_boot_test")
    monkeypatch.setenv("APP_PASSWORD", _APP_PW)
    monkeypatch.setenv("API_PASSWORD", _API_PW)


def test_bootstrap_provisions_smoke_tests_and_writes_tfvars(monkeypatch, tmp_path, provisioned):
    _set_admin_env(monkeypatch)
    tfvars = tmp_path / "terraform.tfvars"

    assert bootstrap.main(tfvars_path=tfvars) == 0

    content = tfvars.read_text(encoding="utf-8")
    assert f'litmuz_app_password = "{_APP_PW}"' in content
    assert f'litmuz_api_password = "{_API_PW}"' in content

    # Idempotent: a second run succeeds and does not duplicate the keys.
    assert bootstrap.main(tfvars_path=tfvars) == 0
    assert tfvars.read_text(encoding="utf-8").count("litmuz_app_password =") == 1


def test_bootstrap_requires_the_admin_password(monkeypatch, tmp_path):
    monkeypatch.delenv("ADMIN_PGPASSWORD", raising=False)
    assert bootstrap.main(tfvars_path=tmp_path / "x.tfvars") == 2


def test_write_tfvars_upserts_without_duplicating(tmp_path):
    path = tmp_path / "terraform.tfvars"
    bootstrap.write_tfvars(path, {"litmuz_app_password": "one"})
    bootstrap.write_tfvars(path, {"litmuz_app_password": "two"})
    text = path.read_text(encoding="utf-8")
    assert text.count("litmuz_app_password =") == 1
    assert 'litmuz_app_password = "two"' in text
