from __future__ import annotations

from typing import Optional
from devmemory.attribution.sqlite_storage import SQLiteAttributionStorage
from devmemory.core.logging_config import get_logger

log = get_logger(__name__)


class AttributionStorage:
    """
    Unified attribution storage interface.

    Local mode only: SQLite storage
    Cloud mode will be implemented via HTTP API client (separate module)
    """

    def __init__(self, storage_type: str = "sqlite", **kwargs):
        """
        Initialize attribution storage.

        Args:
            storage_type: Only "sqlite" supported in local mode
            **kwargs: Additional arguments passed to the underlying storage
        """
        if storage_type != "sqlite":
            raise ValueError(
                f"Storage type '{storage_type}' not supported in local mode. "
                f"Local mode only supports 'sqlite'. "
                f"For cloud features, use 'devmemory install --mode cloud --api-key YOUR_KEY'"
            )

        self.storage_type = storage_type
        db_path = kwargs.get("db_path", "")
        self._storage: SQLiteAttributionStorage = SQLiteAttributionStorage(db_path)
        log.debug(f"AttributionStorage: initialized SQLite backend at {db_path}")

    def store_attribution(
        self,
        namespace: str,
        filepath: str,
        commit_sha: str,
        author_email: str,
        line_ranges: dict[str, dict],
        commit_timestamp: Optional[int] = None,
    ) -> None:
        """Store line-level attribution for a file."""
        return self._storage.store_attribution(
            namespace=namespace,
            filepath=filepath,
            commit_sha=commit_sha,
            author_email=author_email,
            line_ranges=line_ranges,
            commit_timestamp=commit_timestamp,
        )

    def get_attribution(
        self,
        namespace: str,
        filepath: str,
        commit_sha: str,
        lineno: int,
    ) -> Optional[dict]:
        """Get attribution for a specific line in a specific commit."""
        return self._storage.get_attribution(
            namespace=namespace,
            filepath=filepath,
            commit_sha=commit_sha,
            lineno=lineno,
        )

    def get_latest_attribution(
        self,
        namespace: str,
        filepath: str,
        lineno: int,
        fallback_depth: int = 10,
    ) -> Optional[dict]:
        """
        Get the latest attribution for a specific line.

        This is the primary method for Sentry lookups - no commit SHA needed!
        """
        return self._storage.get_latest_attribution(
            namespace=namespace,
            filepath=filepath,
            lineno=lineno,
            fallback_depth=fallback_depth,
        )

    def get_file_history(
        self,
        namespace: str,
        filepath: str,
        limit: int = 50,
    ) -> list[dict]:
        """Get commit history for a file."""
        return self._storage.get_file_history(
            namespace=namespace,
            filepath=filepath,
            limit=limit,
        )

    def get_file_attribution_summary(
        self,
        namespace: str,
        filepath: str,
        commit_sha: str,
    ) -> Optional[dict]:
        """Get summary of AI vs human lines for a file."""
        return self._storage.get_file_attribution_summary(
            namespace=namespace,
            filepath=filepath,
            commit_sha=commit_sha,
        )

    def close(self) -> None:
        """Close storage connection."""
        self._storage.close()
