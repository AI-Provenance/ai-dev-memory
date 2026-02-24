"""
DevMemory Sentry Processor

Enriches Sentry events with AI attribution data from DevMemory Redis.

Usage:
    from devmemory.sentry import create_before_send

    Sentry.init({
        "dsn": "...",
        "release": os.environ["APP_VERSION"],  # Must be commit SHA!
        "before_send": create_before_send(
            ams_url="https://ams.internal",
            # repo_id is auto-detected from git if not provided
        )
    })

Installation:
    pip install devmemory[sentry]
"""

from __future__ import annotations

import os
from typing import Any, Awaitable, Callable, Optional

# Type aliases for the callback
Event = dict[str, Any]
Hint = dict[str, Any]
BeforeSend = Callable[[Event, Hint], Awaitable[Event]]


def _get_repo_id() -> str:
    """Auto-detect repo_id from git, fallback to environment or 'unknown'."""
    # Try to get from git
    try:
        from devmemory.core.utils import get_repo_id as _get_git_repo_id

        repo_id = _get_git_repo_id()
        if repo_id and repo_id != "non-git":
            return repo_id
    except Exception:
        pass

    # Fallback to environment variable
    env_repo_id = os.environ.get("DEVMEMORY_REPO_ID")
    if env_repo_id:
        return env_repo_id

    # Final fallback
    return "unknown"


class DevMemoryOptions:
    """Configuration options for DevMemory Sentry processor."""

    def __init__(
        self,
        ams_url: Optional[str] = None,
        repo_id: Optional[str] = None,
        timeout: float = 2.0,
        enabled: bool = True,
    ):
        self.ams_url = ams_url or os.environ.get("DEVMEMORY_AMS_URL", "http://localhost:8000")

        # Auto-detect repo_id if not provided
        if repo_id:
            self.repo_id = repo_id
        else:
            self.repo_id = _get_repo_id()

        self.timeout = timeout
        self.enabled = enabled and bool(self.repo_id)

    def validate(self) -> bool:
        """Check if configuration is valid."""
        if not self.enabled:
            return False
        if not self.ams_url:
            return False
        if not self.repo_id or self.repo_id == "unknown":
            return False
        return True


def create_before_send(
    ams_url: Optional[str] = None,
    repo_id: Optional[str] = None,
    timeout: float = 2.0,
) -> Optional[BeforeSend]:
    """
    Create a Sentry before_send hook that enriches events with AI attribution.

    Args:
        ams_url: URL of the DevMemory AMS API (or attribution endpoint)
        repo_id: Repository identifier (maps to Redis namespace)
        timeout: Request timeout in seconds (default: 2s)

    Returns:
        A before_send function for Sentry.init(), or None if not configured

    Example:
        from sentry_sdk import init
        from devmemory.sentry import create_before_send

        init(
            dsn=os.environ["SENTRY_DSN"],
            release=os.environ["APP_VERSION"],  # Commit SHA!
            before_send=create_before_send(
                ams_url="https://ams.internal",
                repo_id="payments-service"
            )
        )
    """
    options = DevMemoryOptions(
        ams_url=ams_url,
        repo_id=repo_id,
        timeout=timeout,
    )

    if not options.validate():
        return None

    async def before_send(event: Event, hint: Hint) -> Event:
        """Sentry before_send hook to add AI attribution."""
        release = event.get("release")
        if not release:
            return event

        try:
            frame = _extract_first_in_app_frame(event)
            if not frame:
                return event

            filepath = frame.get("filename") or frame.get("abs_path", "")
            lineno = frame.get("lineno")

            if not filepath or not lineno:
                return event

            attribution = await _lookup_attribution(
                ams_url=options.ams_url,
                repo_id=options.repo_id,
                release=release,
                filepath=filepath,
                lineno=lineno,
                timeout=options.timeout,
            )

            if attribution:
                event["tags"] = event.get("tags", {})
                event["tags"]["ai_origin"] = attribution.get("author", "human")
                event["tags"]["ai_tool"] = attribution.get("tool", "unknown")
                event["tags"]["ai_confidence"] = attribution.get("confidence", 0)

                event["contexts"] = event.get("contexts", {})
                event["contexts"]["ai_attribution"] = {
                    "author": attribution.get("author", "human"),
                    "tool": attribution.get("tool"),
                    "model": attribution.get("model"),
                    "confidence": attribution.get("confidence"),
                    "commit_sha": attribution.get("commit_sha"),
                    "filepath": filepath,
                    "lineno": lineno,
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


async def _lookup_attribution(
    ams_url: str,
    repo_id: str,
    release: str,
    filepath: str,
    lineno: int,
    timeout: float,
) -> Optional[dict]:
    """Call DevMemory attribution API."""
    try:
        import httpx
    except ImportError:
        return None

    url = f"{ams_url}/api/v1/attribution/lookup"

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                url,
                json={
                    "release": release,
                    "repo_id": repo_id,
                    "filepath": filepath,
                    "lineno": lineno,
                },
            )

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                return None
            else:
                return None

    except Exception:
        return None
