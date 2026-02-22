from __future__ import annotations

import httpx
from dataclasses import dataclass
from typing import Optional
from contextlib import contextmanager
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from devmemory.core.logging_config import get_logger

log = get_logger(__name__)


def _is_retryable_http_error(exception: BaseException) -> bool:
    """Return True for connection errors and 5xx server errors."""
    if isinstance(exception, httpx.ConnectError):
        return True
    if isinstance(exception, httpx.ReadTimeout):
        return True
    if isinstance(exception, httpx.HTTPStatusError):
        return exception.response.status_code >= 500
    return False


retry_on_network_error = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(httpx.ConnectError) | retry_if_exception_type(httpx.ReadTimeout),
    reraise=True,
)


@dataclass
class MemoryResult:
    id: str
    text: str
    score: float
    topics: list[str]
    entities: list[str]
    memory_type: str
    created_at: str
    user_id: str = ""
    namespace: str = ""
    session_id: str = ""


@dataclass
class SummaryView:
    id: str
    name: Optional[str] = None
    source: str = "long_term"
    group_by: list[str] = None
    filters: dict = None
    time_window_days: Optional[int] = None
    continuous: bool = False
    prompt: Optional[str] = None
    model_name: Optional[str] = None


class AMSClient:
    def __init__(self, base_url: str = "http://localhost:8000", timeout: float = 30.0, auth_token: str = ""):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.auth_token = auth_token
        self._shared_client: httpx.Client | None = None

    def _get_headers(self) -> dict:
        headers = {}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        return headers

    def _get_client(self) -> httpx.Client:
        if self._shared_client:
            return self._shared_client
        return httpx.Client(base_url=self.base_url, timeout=self.timeout, headers=self._get_headers())

    @contextmanager
    def _client_context(self):
        client = httpx.Client(base_url=self.base_url, timeout=self.timeout, headers=self._get_headers())
        try:
            yield client
        finally:
            client.close()

    def __enter__(self):
        self._shared_client = httpx.Client(base_url=self.base_url, timeout=self.timeout, headers=self._get_headers())
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._shared_client:
            self._shared_client.close()
            self._shared_client = None

    @retry_on_network_error
    def health_check(self) -> dict:
        log.debug(f"health_check: {self.base_url}")
        client = self._get_client()
        resp = client.get("/v1/health")
        resp.raise_for_status()
        result = resp.json()
        log.debug(f"health_check: success")
        return result

    @retry_on_network_error
    def create_memories(
        self,
        memories: list[dict],
        deduplicate: bool = True,
    ) -> dict:
        if not memories:
            log.debug("create_memories: empty list, skipping")
            return {"count": 0, "ids": []}

        log.info(f"create_memories: sending {len(memories)} memories (deduplicate={deduplicate})")
        payload = {
            "memories": memories,
            "deduplicate": deduplicate,
        }
        client = self._get_client()
        try:
            resp = client.post("/v1/long-term-memory/", json=payload)
            resp.raise_for_status()
            result = resp.json()
            log.info(f"create_memories: created {result.get('count', 0)} memories")
            return result
        except httpx.HTTPStatusError as e:
            log.error(f"create_memories: HTTP {e.response.status_code} - {e.response.text[:200]}")
            raise
        except httpx.ConnectError as e:
            log.error(f"create_memories: connection failed to {self.base_url}")
            raise

    @retry_on_network_error
    def search_memories(
        self,
        text: str,
        limit: int = 10,
        namespace: str | None = None,
        user_id: str | None = None,
        topics: list[str] | None = None,
        memory_type: str | None = None,
    ) -> list[MemoryResult]:
        log.debug(f"search_memories: query='{text[:50]}...' limit={limit} namespace={namespace}")
        payload: dict = {
            "text": text,
            "limit": limit,
        }
        if namespace:
            payload["namespace"] = {"eq": namespace}
        if user_id:
            payload["user_id"] = {"eq": user_id}
        if topics:
            payload["topics"] = {"any": topics}
        if memory_type:
            payload["memory_type"] = {"eq": memory_type}

        log.debug(f"search_memories: payload={payload}")

        try:
            if self._shared_client:
                client = self._shared_client
                resp = client.post("/v1/long-term-memory/search", json=payload)
                resp.raise_for_status()
                data = resp.json()
            else:
                with self._client_context() as client:
                    resp = client.post("/v1/long-term-memory/search", json=payload)
                    resp.raise_for_status()
                    data = resp.json()

            results = []
            for m in data.get("memories", []):
                results.append(
                    MemoryResult(
                        id=m.get("id", ""),
                        text=m.get("text", ""),
                        score=m.get("dist", m.get("score", 0.0)),
                        topics=m.get("topics") or [],
                        entities=m.get("entities") or [],
                        memory_type=m.get("memory_type", ""),
                        created_at=m.get("created_at") or m.get("metadata", {}).get("created_at", ""),
                        user_id=m.get("user_id", ""),
                        namespace=m.get("namespace", ""),
                        session_id=m.get("session_id", ""),
                    )
                )
            log.debug(f"search_memories: found {len(results)} results")
            return results
        except httpx.HTTPStatusError as e:
            log.error(f"search_memories: HTTP {e.response.status_code}")
            raise
        except httpx.ConnectError:
            log.error(f"search_memories: connection failed to {self.base_url}")
            raise

    def get_memory_count(self, namespace: str | None = None) -> int:
        log.debug(f"get_memory_count: namespace={namespace}")
        try:
            total = 0
            offset = 0
            if self._shared_client:
                client = self._shared_client
                while True:
                    payload: dict = {"text": "", "limit": 100, "offset": offset}
                    if namespace:
                        payload["namespace"] = {"eq": namespace}
                    resp = client.post("/v1/long-term-memory/search", json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                    total += len(data.get("memories", []))
                    if data.get("next_offset") is None:
                        break
                    offset = data["next_offset"]
            else:
                with self._client_context() as client:
                    while True:
                        payload: dict = {"text": "", "limit": 100, "offset": offset}
                        if namespace:
                            payload["namespace"] = {"eq": namespace}
                        resp = client.post("/v1/long-term-memory/search", json=payload)
                        resp.raise_for_status()
                        data = resp.json()
                        total += len(data.get("memories", []))
                        if data.get("next_offset") is None:
                            break
                        offset = data["next_offset"]
            log.debug(f"get_memory_count: total={total}")
            return total
        except Exception as e:
            log.warning(f"get_memory_count: failed - {e}")
            return -1

    def list_sessions(self, namespace: str | None = None, limit: int = 50) -> list[str]:
        params: dict = {"limit": limit}
        if namespace:
            params["namespace"] = namespace
        if self._shared_client:
            client = self._shared_client
            resp = client.get("/v1/working-memory/", params=params)
            resp.raise_for_status()
            return resp.json().get("sessions", [])
        else:
            with self._client_context() as client:
                resp = client.get("/v1/working-memory/", params=params)
                resp.raise_for_status()
                return resp.json().get("sessions", [])

    def list_summary_views(self) -> list[SummaryView]:
        if self._shared_client:
            client = self._shared_client
            resp = client.get("/v1/summary-views")
            resp.raise_for_status()
            data = resp.json()
            return [SummaryView(**view) for view in data]
        else:
            with self._client_context() as client:
                resp = client.get("/v1/summary-views")
                resp.raise_for_status()
                data = resp.json()
                return [SummaryView(**view) for view in data]

    def create_summary_view(self, view_config: dict) -> SummaryView:
        if self._shared_client:
            client = self._shared_client
            resp = client.post("/v1/summary-views", json=view_config)
            resp.raise_for_status()
            return SummaryView(**resp.json())
        else:
            with self._client_context() as client:
                resp = client.post("/v1/summary-views", json=view_config)
                resp.raise_for_status()
                return SummaryView(**resp.json())

    def get_summary_view(self, view_id: str) -> SummaryView:
        if self._shared_client:
            client = self._shared_client
            resp = client.get(f"/v1/summary-views/{view_id}")
            resp.raise_for_status()
            return SummaryView(**resp.json())
        else:
            with self._client_context() as client:
                resp = client.get(f"/v1/summary-views/{view_id}")
                resp.raise_for_status()
                return SummaryView(**resp.json())

    def delete_summary_view(self, view_id: str) -> dict:
        if self._shared_client:
            client = self._shared_client
            resp = client.delete(f"/v1/summary-views/{view_id}")
            resp.raise_for_status()
            return resp.json()
        else:
            with self._client_context() as client:
                resp = client.delete(f"/v1/summary-views/{view_id}")
                resp.raise_for_status()
                return resp.json()

    def get_summary_view_partitions(self, view_id: str, user_id: str = None) -> list[dict]:
        """Get partition results from a summary view."""
        params = {}
        if user_id:
            params["user_id"] = user_id

        if self._shared_client:
            client = self._shared_client
            resp = client.get(f"/v1/summary-views/{view_id}/partitions", params=params)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list):
                return data
            return data.get("partitions", [])
        else:
            with self._client_context() as client:
                resp = client.get(f"/v1/summary-views/{view_id}/partitions", params=params)
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, list):
                    return data
                return data.get("partitions", [])

    def run_summary_view_partition(self, view_id: str, group: dict) -> dict:
        """Run a specific partition of a summary view."""
        if self._shared_client:
            client = self._shared_client
            resp = client.post(f"/v1/summary-views/{view_id}/partitions/run", json={"group": group})
            resp.raise_for_status()
            return resp.json()
        else:
            with self._client_context() as client:
                resp = client.post(f"/v1/summary-views/{view_id}/partitions/run", json={"group": group})
                resp.raise_for_status()
                return resp.json()
