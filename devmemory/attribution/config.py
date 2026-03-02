from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv
from devmemory.core.logging_config import get_logger

log = get_logger(__name__)

_dotenv_loaded = False


def _ensure_dotenv_loaded():
    global _dotenv_loaded
    if _dotenv_loaded:
        return

    env_paths = [
        Path.cwd() / ".env",
        Path.home() / ".devmemory" / ".env",
    ]

    for env_path in env_paths:
        if env_path.exists():
            load_dotenv(env_path)
            log.debug(f"Loaded .env from {env_path}")
            break

    _dotenv_loaded = True


@dataclass
class AttributionConfig:
    """Configuration for attribution storage."""

    sqlite_path: str = ""
    redis_url: str = ""  # Legacy - optional

    @classmethod
    def load(cls) -> AttributionConfig:
        """Load attribution config from environment.

        Primary storage is SQLite. Redis is optional and only used if explicitly configured.
        """
        _ensure_dotenv_loaded()

        # SQLite path (primary)
        sqlite_path = os.environ.get("DEVMEMORY_SQLITE_PATH", "")

        # Redis URL (optional - legacy)
        redis_url = os.environ.get("REDIS_URL", "")

        if not redis_url:
            redis_host = os.environ.get("REDIS_HOST")
            if redis_host:
                redis_port = os.environ.get("REDIS_PORT", "6379")
                redis_pass = os.environ.get("REDIS_PASSWORD", "")
                redis_user = os.environ.get("REDIS_USERNAME", "")

                if redis_pass:
                    if redis_user:
                        redis_url = f"redis://{redis_user}:{redis_pass}@{redis_host}:{redis_port}"
                    else:
                        redis_url = f"redis://:{redis_pass}@{redis_host}:{redis_port}"
                else:
                    redis_url = f"redis://{redis_host}:{redis_port}"

        if sqlite_path:
            log.debug(f"AttributionConfig: sqlite_path={sqlite_path}")
        if redis_url:
            log.debug(f"AttributionConfig: redis_url={_mask_password(redis_url)}")

        return cls(sqlite_path=sqlite_path, redis_url=redis_url)


def _mask_password(url: str) -> str:
    """Mask password in Redis URL for logging."""
    if "@" in url:
        parts = url.split("@")
        creds = parts[0].split("://")
        if ":" in creds[-1]:
            user, _ = creds[-1].split(":", 1)
            return f"{creds[0]}://{user}:***@{parts[1]}"
    return url
