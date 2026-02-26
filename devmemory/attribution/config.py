from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv
from devmemory.core.logging_config import get_logger

log = get_logger(__name__)

# Load .env file if it exists
_dotenv_loaded = False


def _ensure_dotenv_loaded():
    global _dotenv_loaded
    if _dotenv_loaded:
        return

    # Try to load from current directory or home directory
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

    redis_url: str
    is_local_mode: bool = False
    sqlite_path: str = ""

    @classmethod
    def load(cls) -> AttributionConfig:
        """
        Load attribution config from environment.

        Supports multiple configuration methods (in order of priority):
        1. REDIS_URL with embedded credentials (redis://user:pass@host:port)
        2. REDIS_HOST + REDIS_PORT + optional REDIS_PASSWORD
        3. Derived from AMS_ENDPOINT (if AMS_ENDPOINT points to localhost)
        4. Default: redis://localhost:6379
        """
        # Ensure .env is loaded
        _ensure_dotenv_loaded()
        # Priority 1: Explicit REDIS_URL
        redis_url = os.environ.get("REDIS_URL")

        if not redis_url:
            # Priority 2: Build from separate components
            redis_host = os.environ.get("REDIS_HOST")
            if redis_host:
                redis_port = os.environ.get("REDIS_PORT", "6379")
                redis_user = os.environ.get("REDIS_USERNAME", "")
                redis_pass = os.environ.get("REDIS_PASSWORD", "")

                if redis_pass:
                    if redis_user:
                        redis_url = f"redis://{redis_user}:{redis_pass}@{redis_host}:{redis_port}"
                    else:
                        redis_url = f"redis://:{redis_pass}@{redis_host}:{redis_port}"
                else:
                    redis_url = f"redis://{redis_host}:{redis_port}"
            else:
                # Priority 3: Derive from AMS_ENDPOINT
                ams_endpoint = os.environ.get("AMS_ENDPOINT", "http://localhost:8000")
                if ams_endpoint.startswith("http://localhost") or "localhost" in ams_endpoint:
                    redis_url = "redis://localhost:6379"
                else:
                    # For remote AMS, use the same host but redis protocol
                    host = ams_endpoint.replace("http://", "").replace("https://", "").split(":")[0]
                    port = (
                        ams_endpoint.replace("http://", "").replace("https://", "").split(":")[1]
                        if ":" in ams_endpoint
                        else "6379"
                    )
                    redis_url = f"redis://{host}:{port}"

        # Priority 4: Default
        if not redis_url:
            redis_url = "redis://localhost:6379"

        log.debug(f"AttributionConfig: redis_url={_mask_password(redis_url)}")

        # Check for local mode configuration
        is_local_mode = os.environ.get("DEVMEMORY_MODE", "").lower() == "local"
        sqlite_path = os.environ.get("DEVMEMORY_SQLITE_PATH", "")

        return cls(redis_url=redis_url, is_local_mode=is_local_mode, sqlite_path=sqlite_path)


def _mask_password(url: str) -> str:
    """Mask password in Redis URL for logging."""
    if "@" in url:
        parts = url.split("@")
        creds = parts[0].split("://")
        if ":" in creds[-1]:
            user, _ = creds[-1].split(":", 1)
            return f"{creds[0]}://{user}:***@{parts[1]}"
    return url
