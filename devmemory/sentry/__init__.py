"""
DevMemory Sentry Processor

Enriches Sentry events with AI attribution data from DevMemory Redis.

Usage:
    from devmemory.sentry import create_before_send

    Sentry.init({
        "dsn": "...",
        "before_send": create_before_send()
    })

In production:
    - DEVMEMORY_AMS_URL must be set (e.g., https://ams.internal)
    - repo_id is auto-detected from devmemory config if available, otherwise from DEVMEMORY_REPO_ID
    - NO release configuration needed!

Installation:
    pip install devmemory[sentry]
"""

from __future__ import annotations

import os
from typing import Any, Callable, Optional

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
    ):
        """
        Initialize options.

        Args:
            ams_url: URL of the attribution API. Required - set via DEVMEMORY_AMS_URL env var.
            repo_id: Repository identifier. Auto-detected if not provided.
            timeout: Request timeout in seconds.
        """
        self.ams_url = ams_url or _get_ams_url()
        self.repo_id = repo_id or _get_repo_id()
        self.timeout = timeout

    def validate(self) -> bool:
        """Check if configuration is valid."""
        if not self.ams_url:
            return False
        if not self.repo_id:
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

    def before_send(event: Event, hint: Hint) -> Event:
        """
        Sentry before_send hook to add AI attribution.

        Note: No release needed! API uses latest attribution for the file.
        """
        try:
            frame = _extract_first_in_app_frame(event)
            if not frame:
                return event

            filepath = frame.get("filename") or frame.get("abs_path", "")
            lineno = frame.get("lineno")

            if not filepath or not lineno:
                return event

            attribution = _lookup_attribution_sync(
                ams_url=options.ams_url,
                repo_id=options.repo_id,
                filepath=filepath,
                lineno=lineno,
                timeout=options.timeout,
            )

            # Only tag if we have attribution data
            if attribution and attribution.get("author"):
                author = attribution.get("author")

                # If author is "human" from API, it means we looked but found no AI
                # Keep it as human (known to be written by human)
                # If no attribution at all, author will be empty/None

                event["tags"] = event.get("tags", {})
                event["tags"]["ai_origin"] = author if author else "unknown"
                event["tags"]["ai_tool"] = attribution.get("tool") or "unknown"
                event["tags"]["ai_confidence"] = attribution.get("confidence", 0)
                if attribution.get("prompt_id"):
                    event["tags"]["ai_prompt_id"] = attribution.get("prompt_id")

                event["contexts"] = event.get("contexts", {})
                event["contexts"]["ai_attribution"] = {
                    "author": author if author else "unknown",
                    "tool": attribution.get("tool"),
                    "model": attribution.get("model"),
                    "prompt_id": attribution.get("prompt_id"),
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


def _lookup_attribution_sync(
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
