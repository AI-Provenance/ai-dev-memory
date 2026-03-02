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

    def explain_why(
        self, filepath: str, function: str = "", limit: int = 15, raw: bool = False, verbose: bool = False
    ) -> dict:
        """Explain why a file exists and how it evolved.

        Args:
            filepath: Path to file
            function: Optional function name
            limit: Max memories to use
            raw: Show raw results
            verbose: Verbose output

        Returns:
            Explanation data from API
        """
        try:
            response = self.session.post(
                f"{self.base_url}/v1/why",
                json={"filepath": filepath, "function": function, "limit": limit, "raw": raw, "verbose": verbose},
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            log.error(f"Why query failed: {e}")
            return {"error": str(e), "message": "Why command requires Cloud Edition"}

    def add_memory(
        self, text: str, memory_type: str = "semantic", topics: Optional[list] = None, entities: Optional[list] = None
    ) -> dict:
        """Add a memory to the store.

        Args:
            text: Memory text
            memory_type: Type of memory
            topics: Topic tags
            entities: Entity tags

        Returns:
            Result from API
        """
        try:
            response = self.session.post(
                f"{self.base_url}/v1/add",
                json={"text": text, "memory_type": memory_type, "topics": topics or [], "entities": entities or []},
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            log.error(f"Add memory failed: {e}")
            return {"error": str(e), "message": "Add command requires Cloud Edition"}

    def learn_knowledge(self, path: str = ".devmemory/knowledge", dry_run: bool = False) -> dict:
        """Learn from knowledge files.

        Args:
            path: Path to knowledge directory
            dry_run: Don't actually sync

        Returns:
            Result from API
        """
        try:
            response = self.session.post(f"{self.base_url}/v1/learn", json={"path": path, "dry_run": dry_run})
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            log.error(f"Learn failed: {e}")
            return {"error": str(e), "message": "Learn command requires Cloud Edition"}

    def generate_context(self, output: str = ".devmemory/CONTEXT.md", quiet: bool = False) -> dict:
        """Generate context from memories.

        Args:
            output: Output file path
            quiet: Minimal output

        Returns:
            Result from API
        """
        try:
            response = self.session.post(f"{self.base_url}/v1/context", json={"output": output, "quiet": quiet})
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            log.error(f"Context generation failed: {e}")
            return {"error": str(e), "message": "Context command requires Cloud Edition"}

    def summarize(
        self,
        view_type: str = "project",
        namespace: str = "default",
        time_window: Optional[int] = None,
        manual: bool = False,
        custom_prompt: Optional[str] = None,
    ) -> dict:
        """Create a project summary.

        Args:
            view_type: Type of summary ("project" or "architecture")
            namespace: Namespace to summarize
            time_window: Time window in days
            manual: Generate manual summary from commits
            custom_prompt: Custom prompt for summary generation

        Returns:
            Summary result from API
        """
        try:
            response = self.session.post(
                f"{self.base_url}/v1/summarize",
                json={
                    "view_type": view_type,
                    "namespace": namespace,
                    "time_window": time_window,
                    "manual": manual,
                    "custom_prompt": custom_prompt,
                },
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            log.error(f"Summarize failed: {e}")
            return {"error": str(e), "message": "Summarize command requires Cloud Edition"}

    def list_summary_views(self) -> dict:
        """List all summary views.

        Returns:
            List of summary views from API
        """
        try:
            response = self.session.get(f"{self.base_url}/v1/summarize")
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            log.error(f"List summary views failed: {e}")
            return {"error": str(e), "message": "List views requires Cloud Edition"}

    def delete_summary_view(self, view_id: str) -> dict:
        """Delete a summary view.

        Args:
            view_id: ID of the view to delete

        Returns:
            Deletion result from API
        """
        try:
            response = self.session.delete(f"{self.base_url}/v1/summarize?view_id={view_id}")
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            log.error(f"Delete summary view failed: {e}")
            return {"error": str(e), "message": "Delete view requires Cloud Edition"}

    def generate_architecture_summary(
        self, output: str = ".devmemory/architecture-summary.md", namespace: str = "default", time_window: int = 30
    ) -> dict:
        """Generate architecture summary document.

        Args:
            output: Output file path
            namespace: Namespace to analyze
            time_window: Time window in days

        Returns:
            Architecture summary result from API
        """
        try:
            response = self.session.post(
                f"{self.base_url}/v1/architecture",
                json={"output": output, "namespace": namespace, "time_window": time_window},
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            log.error(f"Architecture summary failed: {e}")
            return {"error": str(e), "message": "Architecture command requires Cloud Edition"}

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
