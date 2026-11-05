"""Application settings loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime configuration read from environment variables."""
    database_url: str
    redis_url: str
    magic_link_secret: str
    base_url: str
    app_env: str
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    smtp_from: str
    contact_email: str

    @property
    def is_test(self) -> bool:
        """Return True when the app runs in the test environment."""
        return self.app_env == "test"


_DEV_SECRET = "dev-secret-change-me"


def _load_settings() -> Settings:
    """Build the process-wide Settings from environment variables."""
    base_url = os.environ.get("BASE_URL", "http://localhost:8787")
    return Settings(
        database_url=os.environ.get(
            "DATABASE_URL",
            "postgresql+asyncpg://localhost:5433/shipswipe",
        ),
        redis_url=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
        magic_link_secret=os.environ.get("MAGIC_LINK_SECRET", _DEV_SECRET),
        base_url=base_url,
        app_env=os.environ.get("APP_ENV", "development"),
        smtp_host=os.environ.get("SMTP_HOST", "localhost"),
        smtp_port=int(os.environ.get("SMTP_PORT", "587")),
        smtp_user=os.environ.get("SMTP_USER", ""),
        smtp_password=os.environ.get("SMTP_PASSWORD", ""),
        smtp_from=os.environ.get("SMTP_FROM", "noreply@example.com"),
        # The legal pages' data-subject contact — a real mailbox, so set it
        # explicitly when the derived support@<host> address doesn't exist.
        contact_email=os.environ.get(
            "CONTACT_EMAIL",
            f"support@{urlparse(base_url).hostname or 'example.com'}",
        ),
    )


def _check_secret(s: Settings) -> None:
    """Refuse to boot a non-dev deployment with a missing or weak signing secret."""
    if s.app_env in ("development", "test"):
        return
    if not s.magic_link_secret or s.magic_link_secret == _DEV_SECRET or len(s.magic_link_secret) < 32:
        raise RuntimeError(
            "MAGIC_LINK_SECRET must be set to a secret of at least 32 characters "
            f"when APP_ENV={s.app_env!r}"
        )


settings = _load_settings()
_check_secret(settings)