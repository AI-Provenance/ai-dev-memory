"""
DevMemory Sentry Processor

Enriches Sentry events with AI attribution data from DevMemory storage.

Supports two modes:
- Local mode: Reads from local SQLite database
- Cloud mode: Calls AMS API for attribution data

Usage:
    from devmemory.sentry import create_before_send

    Sentry.init({
        "dsn": "...",
        "before_send": create_before_send()
    })

In production:
    - Local mode: Set DEVMEMORY_MODE=local and ensure SQLite DB exists
    - Cloud mode: Set DEVMEMORY_AMS_URL (e.g., https://ams.internal)
    - repo_id is auto-detected from devmemory config if available, otherwise from DEVMEMORY_REPO_ID

Installation:
    pip install devmemory[sentry]
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Optional

from devmemory.core.logging_config import get_logger

log = get_logger(__name__)

# Type aliases for the callback
Event = dict[str, Any]
Hint = dict[str, Any]
BeforeSend = Callable[[Event, Hint], Event]


def _get_repo_id() -> str:
    """
    Get repo_id for attribution queries.

    Priority:
    1. DEVMEMORY_REPO_ID environment variable (production can set this)
    2. devmemory config (if available in production deployment)
    3. Git remote (only works if git is available)
    """
    # Priority 1: Environment variable
    env_repo_id = os.environ.get("DEVMEMORY_REPO_ID")
    if env_repo_id:
        return env_repo_id

    # Priority 2: Try devmemory config (works in production if config is deployed)
    try:
        from devmemory.core.config import DevMemoryConfig

        config = DevMemoryConfig.load()
        ns = config.get_active_namespace()
        if ns and ns != "non-git":
            return ns
    except Exception:
        pass

    # Priority 3: Try git remote (usually not available in production pods)
    try:
        import subprocess

        result = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True, text=True, timeout=2)
        if result.returncode == 0 and result.stdout.strip():
            remote_url = result.stdout.strip()
            import re

            clean_id = re.sub(r"[^a-zA-Z0-9]", "-", remote_url)
            return clean_id.strip("-")
    except Exception:
        pass

    # No way to determine repo_id
    return ""


def _get_mode() -> str:
    """Get the installation mode: 'local' or 'cloud'."""
    # Check environment variable first
    mode = os.environ.get("DEVMEMORY_MODE", "").lower()
    if mode in ("local", "cloud"):
        return mode

    # Try to get from config
    try:
        from devmemory.core.config import DevMemoryConfig

        config = DevMemoryConfig.load()
        if config.installation_mode:
            return config.installation_mode
    except Exception:
        pass

    # Default to cloud mode
    return "cloud"


def _get_sqlite_path() -> str:
    """Get the SQLite database path for local mode."""
    # Check environment variable first
    sqlite_path = os.environ.get("DEVMEMORY_SQLITE_PATH", "")
    if sqlite_path:
        return sqlite_path

    # Try to get from config
    try:
        from devmemory.core.config import DevMemoryConfig

        config = DevMemoryConfig.load()
        if config.sqlite_path:
            return config.sqlite_path
        # Get default path from config
        if config.get_sqlite_path():
            return config.get_sqlite_path()
    except Exception:
        pass

    # Try to find .devmemory in current directory or parent
    cwd = Path.cwd()
    for path in [cwd] + list(cwd.parents):
        devmemory_dir = path / ".devmemory"
        if devmemory_dir.exists():
            return str(devmemory_dir / "attributions.db")

    # Default path
    return ".devmemory/attributions.db"


def _get_ams_url() -> str:
    """
    Get AMS URL from environment variable.

    In production, this MUST be set via DEVMEMORY_AMS_URL env var.
    """
    return os.environ.get("DEVMEMORY_AMS_URL", "")


class DevMemoryOptions:
    """Configuration options for DevMemory Sentry processor."""

    def __init__(
        self,
        ams_url: Optional[str] = None,
        repo_id: Optional[str] = None,
        timeout: float = 2.0,
        mode: Optional[str] = None,
        sqlite_path: Optional[str] = None,
    ):
        """
        Initialize options.

        Args:
            ams_url: URL of the attribution API. Required for cloud mode.
            repo_id: Repository identifier. Auto-detected if not provided.
            timeout: Request timeout in seconds.
            mode: "local" or "cloud". Auto-detected if not provided.
            sqlite_path: Path to SQLite database for local mode.
        """
        self.mode = mode or _get_mode()
        self.ams_url = ams_url or _get_ams_url()
        self.repo_id = repo_id or _get_repo_id()
        self.timeout = timeout
        self.sqlite_path = sqlite_path or _get_sqlite_path()

    def validate(self) -> bool:
        """Check if configuration is valid."""
        if self.mode == "cloud":
            if not self.ams_url:
                log.warning("DevMemory Sentry: Cloud mode requires AMS_URL")
                return False
            if not self.repo_id:
                log.warning("DevMemory Sentry: repo_id is required")
                return False
        elif self.mode == "local":
            if not self.repo_id:
                log.warning("DevMemory Sentry: repo_id is required for local mode")
                return False
            # SQLite path is optional, will use default if not found
        return True

    def get_storage_info(self) -> dict:
        """Get storage information for debugging."""
        return {
            "mode": self.mode,
            "ams_url": self.ams_url,
            "repo_id": self.repo_id,
            "sqlite_path": self.sqlite_path if self.mode == "local" else None,
        }


def create_before_send(
    ams_url: Optional[str] = None,
    repo_id: Optional[str] = None,
    timeout: float = 2.0,
    mode: Optional[str] = None,
    sqlite_path: Optional[str] = None,
) -> Optional[BeforeSend]:
    """
    Create a Sentry before_send hook that enriches events with AI attribution.

    Args:
        ams_url: URL of the DevMemory AMS API (cloud mode)
        repo_id: Repository identifier (maps to namespace)
        timeout: Request timeout in seconds (default: 2s)
        mode: "local" or "cloud". Auto-detected if not provided.
        sqlite_path: Path to SQLite database (local mode)

    Returns:
        A before_send function for Sentry.init(), or None if not configured

    Example:
        from sentry_sdk import init
        from devmemory.sentry import create_before_send

        # Local mode (default if DEVMEMORY_MODE=local)
        init(
            dsn=os.environ["SENTRY_DSN"],
            before_send=create_before_send(
                repo_id="my-repo",
                mode="local",
                sqlite_path="/path/to/attributions.db"
            )
        )

        # Cloud mode
        init(
            dsn=os.environ["SENTRY_DSN"],
            before_send=create_before_send(
                ams_url="https://ams.internal",
                repo_id="my-repo",
                mode="cloud"
            )
        )
    """
    options = DevMemoryOptions(
        ams_url=ams_url,
        repo_id=repo_id,
        timeout=timeout,
        mode=mode,
        sqlite_path=sqlite_path,
    )

    if not options.validate():
        log.warning(f"DevMemory Sentry: Invalid configuration: {options.get_storage_info()}")
        return None

    log.info(f"DevMemory Sentry initialized: {options.get_storage_info()}")

    # Pre-create storage for local mode
    local_storage = None
    if options.mode == "local":
        try:
            from devmemory.attribution.sqlite_storage import SQLiteAttributionStorage

            local_storage = SQLiteAttributionStorage(options.sqlite_path)
            # Test connection (sync)
            local_storage._get_conn()
            log.info(f"DevMemory Sentry: Connected to SQLite at {options.sqlite_path}")
        except Exception as e:
            log.warning(f"DevMemory Sentry: Failed to connect to SQLite: {e}")
            local_storage = None

    def before_send(event: Event, hint: Hint) -> Event:
        """
        Sentry before_send hook to add AI attribution.

        Note: No release needed! Uses latest attribution for the file.
        """
        try:
            frame = _extract_first_in_app_frame(event)
            if not frame:
                return event

            filepath = frame.get("filename") or frame.get("abs_path", "")
            lineno = frame.get("lineno")

            if not filepath or not lineno:
                return event

            # Route to appropriate lookup based on mode
            if options.mode == "local":
                attribution = _lookup_from_sqlite(
                    storage=local_storage,
                    repo_id=options.repo_id,
                    filepath=filepath,
                    lineno=lineno,
                )
            else:
                attribution = _lookup_from_api(
                    ams_url=options.ams_url,
                    repo_id=options.repo_id,
                    filepath=filepath,
                    lineno=lineno,
                    timeout=options.timeout,
                )

            # Only tag if we have attribution data
            if attribution and attribution.get("author"):
                author = attribution.get("author")

                # If author is "human" from storage, it means we looked but found no AI
                # Keep it as human (known to be written by human)
                # If no attribution at all, author will be empty/None

                event["tags"] = event.get("tags", {})
                event["tags"]["ai_origin"] = author if author else "unknown"
                event["tags"]["ai_tool"] = attribution.get("tool") or "unknown"
                event["tags"]["ai_confidence"] = attribution.get("confidence", 0)
                if attribution.get("prompt_id"):
                    event["tags"]["ai_prompt_id"] = attribution.get("prompt_id")
                if attribution.get("author_email"):
                    event["tags"]["ai_author_email"] = attribution.get("author_email")

                event["contexts"] = event.get("contexts", {})
                event["contexts"]["ai_attribution"] = {
                    "author": author if author else "unknown",
                    "author_email": attribution.get("author_email"),
                    "tool": attribution.get("tool"),
                    "model": attribution.get("model"),
                    "prompt_id": attribution.get("prompt_id"),
                    "confidence": attribution.get("confidence"),
                    "commit_sha": attribution.get("commit_sha"),
                    "filepath": filepath,
                    "lineno": lineno,
                    "mode": options.mode,
                }

        except Exception:
            pass

        return event

    return before_send


def _extract_first_in_app_frame(event: Event) -> Optional[dict]:
    """Extract the first in-app frame from Sentry event."""
    exception = event.get("exception")
    if exception and exception.get("values"):
        for exc in exception["values"]:
            stacktrace = exc.get("stacktrace")
            if stacktrace and stacktrace.get("frames"):
                for frame in stacktrace["frames"]:
                    if frame.get("in_app"):
                        return frame

    threads = event.get("threads")
    if threads and threads.get("values"):
        for thread in threads["values"]:
            stacktrace = thread.get("stacktrace")
            if stacktrace and stacktrace.get("frames"):
                for frame in stacktrace["frames"]:
                    if frame.get("in_app"):
                        return frame

    return None


def _lookup_from_sqlite(
    storage,
    repo_id: str,
    filepath: str,
    lineno: int,
) -> Optional[dict]:
    """Look up attribution from local SQLite database."""
    if not storage:
        return None

    try:
        # Sync lookup
        result = storage.get_latest_attribution(
            namespace=repo_id,
            filepath=filepath,
            lineno=lineno,
        )

        return result
    except Exception as e:
        log.debug(f"SQLite lookup failed: {e}")
        return None


def _lookup_from_api(
    ams_url: str,
    repo_id: str,
    filepath: str,
    lineno: int,
    timeout: float,
) -> Optional[dict]:
    """Call DevMemory attribution API (synchronous)."""
    try:
        import requests
    except ImportError:
        return None

    url = f"{ams_url}/api/v1/attribution/lookup"

    try:
        response = requests.post(
            url,
            json={
                "repo_id": repo_id,
                "filepath": filepath,
                "lineno": lineno,
            },
            timeout=timeout,
        )

        if response.status_code == 200:
            return response.json()
        elif response.status_code == 404:
            return None
        else:
            return None

    except Exception:
        return None
