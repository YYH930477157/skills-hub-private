from __future__ import annotations

import os
from pathlib import Path


def _bool(name: str, default: str = "false") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    secret: str
    data_dir: Path
    public_url: str
    org_name: str
    owner_email: str
    public_read: bool
    host: str
    port: int
    token_hours: int = 24 * 14

    def __init__(self) -> None:
        root = Path(__file__).resolve().parent.parent
        self.secret = os.environ.get("SKILLHUB_SECRET", "dev-secret-change-me")
        self.data_dir = Path(os.environ.get("SKILLHUB_DATA", str(root / "data"))).resolve()
        self.public_url = os.environ.get("SKILLHUB_PUBLIC_URL", "http://localhost:8000").rstrip("/")
        self.org_name = os.environ.get("SKILLHUB_ORG", "SkillHub")
        self.owner_email = os.environ.get("SKILLHUB_OWNER_EMAIL", "skills@localhost")
        self.public_read = _bool("SKILLHUB_PUBLIC_READ", "true")
        self.host = os.environ.get("SKILLHUB_HOST", "0.0.0.0")
        self.port = int(os.environ.get("SKILLHUB_PORT", "8000"))

    @property
    def db_path(self) -> Path:
        return self.data_dir / "skillhub.db"

    @property
    def packages_dir(self) -> Path:
        return self.data_dir / "packages"

    @property
    def marketplace_dir(self) -> Path:
        return self.data_dir / "marketplace"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.packages_dir.mkdir(parents=True, exist_ok=True)
        self.marketplace_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
