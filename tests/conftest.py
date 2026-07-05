import pytest


@pytest.fixture()
def app_env(tmp_path, monkeypatch):
    """Point the app config at temp dirs and give it a fresh engine + schema."""
    from app import config as config_mod
    from app import db as db_mod

    monkeypatch.setattr(config_mod.config, "data_dir", tmp_path / "config")
    monkeypatch.setattr(config_mod.config, "output_dir", tmp_path / "output")
    monkeypatch.setattr(config_mod.config, "backup_dir", tmp_path / "output" / ".app-backups")
    db_mod.reset_engine()
    db_mod.init_db()
    yield
    db_mod.reset_engine()
