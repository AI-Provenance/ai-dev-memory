"""Cloud storage client for DevMemory API.

This module provides HTTP client for DevMemory Cloud API.
Used in cloud mode to access advanced features.
"""

import requests
from typing import Optional, Any
from devmemory.core.config import DevMemoryConfig
from devmemory.core.logging_config import get_logger

log = get_logger(__name__)


class CloudStorage:
    """HTTP client for DevMemory Cloud API.

    This client connects to aiprove.org API endpoints to provide
    cloud-based features like semantic search, analytics, etc.
    """

    def __init__(self, api_key: str, base_url: str = "https://aiprove.org/api"):
        """Initialize cloud storage client.

        Args:
            api_key: API key for authentication
            base_url: Base URL for API endpoints
        """
        self.api_key = api_key
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "DevMemory-Client/0.1.0",
            }
        )
        log.debug(f"CloudStorage initialized with base_url: {base_url}")

    def health_check(self) -> dict:
        """Check API health status."""
        try:
            response = self.session.get(f"{self.base_url}/health")
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            log.error(f"Health check failed: {e}")
            return {"status": "error", "message": str(e)}

    def search(self, query: str, limit: int = 10, namespace: str = "") -> dict:
        """Search via API.

        Args:
            query: Search query string
            limit: Maximum number of results
            namespace: Optional namespace filter

        Returns:
            Search results from API
        """
        try:
            response = self.session.post(
                f"{self.base_url}/v1/search", json={"query": query, "limit": limit, "namespace": namespace}
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            log.error(f"Search failed: {e}")
            return {"error": str(e), "results": [], "message": "Search requires Cloud Edition"}

    def get_stats(self, days: int = 30) -> dict:
        """Get project statistics.

        Args:
            days: Time window in days

        Returns:
            Statistics data from API
        """
        try:
            response = self.session.get(f"{self.base_url}/v1/stats", params={"days": days})
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            log.error(f"Stats request failed: {e}")
            return {"error": str(e), "message": "Stats requires Cloud Edition"}

    def query_attribution(
        self, filepath: str, line: Optional[int] = None, commit_sha: Optional[str] = None, namespace: str = "default"
    ) -> dict:
        """Query attribution for a file/line.

        Args:
            filepath: Path to file
            line: Optional line number
            commit_sha: Optional commit SHA
            namespace: Namespace for attribution

        Returns:
            Attribution data from API
        """
        try:
            response = self.session.post(
                f"{self.base_url}/v1/attribution/query",
                json={"filepath": filepath, "line": line, "commit_sha": commit_sha, "namespace": namespace},
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            log.error(f"Attribution query failed: {e}")
            return {"error": str(e), "found": False, "message": "Attribution query requires Cloud Edition"}

    def close(self) -> None:
        """Close HTTP session."""
        self.session.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False
