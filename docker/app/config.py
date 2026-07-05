"""Deploy-level configuration, sourced from environment variables.

These are the *infrastructure* settings (where state lives, which port to bind) and
are set by docker-compose. User-editable application settings (output folder,
politeness, defaults) live in the database and are managed via the Settings page —
see ``settings_store.py``.
"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WN_", env_file=".env", extra="ignore")

    # Persistent state (SQLite + settings + cache). Mounted as /config in the container.
    data_dir: Path = Path("/config")
    # Where finished EPUBs are written. Mounted to your books share as /output.
    output_dir: Path = Path("/output")
    # Where daily DB backups land. Deliberately under /output, NOT /config: a botched
    # deploy that wipes appdata must not take the backups with it. Dot-named so ebook
    # library scanners watching the share ignore it. Override with WN_BACKUP_DIR.
    backup_dir: Path = Path("/output/.app-backups")

    host: str = "0.0.0.0"
    port: int = 8080

    @property
    def db_path(self) -> Path:
        return self.data_dir / "app.db"


config = AppConfig()
