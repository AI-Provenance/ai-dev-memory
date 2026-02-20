from __future__ import annotations

import httpx
from dataclasses import dataclass
from typing import Optional


@dataclass
class MemoryResult:
    id: str
    text: str
    score: float
    topics: list[str]
    entities: list[str]
    memory_type: str
    created_at: str


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
    def __init__(self, base_url: str = "http://localhost:8000", timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._shared_client: httpx.Client | None = None

    def _client(self) -> httpx.Client:
        if self._shared_client:
            return self._shared_client
        return httpx.Client(base_url=self.base_url, timeout=self.timeout)

    def __enter__(self):
        self._shared_client = httpx.Client(base_url=self.base_url, timeout=self.timeout)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._shared_client:
            self._shared_client.close()
            self._shared_client = None

    def health_check(self) -> dict:
        client = self._client()
        resp = client.get("/v1/health")
        resp.raise_for_status()
        return resp.json()

    def create_memories(
        self,
        memories: list[dict],
        deduplicate: bool = True,
    ) -> dict:
        if not memories:
            return {"count": 0, "ids": []}

        payload = {
            "memories": memories,
            "deduplicate": deduplicate,
        }
        client = self._client()
        resp = client.post("/v1/long-term-memory/", json=payload)
        resp.raise_for_status()
        return resp.json()

    def search_memories(
        self,
        text: str,
        limit: int = 10,
        namespace: str | None = None,
        user_id: str | None = None,
        topics: list[str] | None = None,
        memory_type: str | None = None,
    ) -> list[MemoryResult]:
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

        with self._client() as client:
            resp = client.post("/v1/long-term-memory/search", json=payload)
            resp.raise_for_status()
            data = resp.json()

        results = []
        for m in data.get("memories", []):
            results.append(MemoryResult(
                id=m.get("id", ""),
                text=m.get("text", ""),
                score=m.get("dist", m.get("score", 0.0)),
                topics=m.get("topics") or [],
                entities=m.get("entities") or [],
                memory_type=m.get("memory_type", ""),
                created_at=m.get("created_at") or m.get("metadata", {}).get("created_at", ""),
            ))
        return results

    def get_memory_count(self, namespace: str | None = None) -> int:
        try:
            total = 0
            offset = 0
            with self._client() as client:
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
            return total
        except Exception:
            return -1

    def list_sessions(self, namespace: str | None = None, limit: int = 50) -> list[str]:
        params: dict = {"limit": limit}
        if namespace:
            params["namespace"] = namespace
        with self._client() as client:
            resp = client.get("/v1/working-memory/", params=params)
            resp.raise_for_status()
            return resp.json().get("sessions", [])

    # Summary View Methods
    def list_summary_views(self) -> list[SummaryView]:
        """List all registered summary views"""
        with self._client() as client:
            resp = client.get("/v1/summary-views")
            resp.raise_for_status()
            data = resp.json()
            return [SummaryView(**view) for view in data]

    def create_summary_view(self, view_config: dict) -> SummaryView:
        """Create a new summary view"""
        with self._client() as client:
            resp = client.post("/v1/summary-views", json=view_config)
            resp.raise_for_status()
            return SummaryView(**resp.json())

    def get_summary_view(self, view_id: str) -> SummaryView:
        """Get a summary view by ID"""
        with self._client() as client:
            resp = client.get(f"/v1/summary-views/{view_id}")
            resp.raise_for_status()
            return SummaryView(**resp.json())

    def delete_summary_view(self, view_id: str) -> dict:
        """Delete a summary view"""
        with self._client() as client:
            resp = client.delete(f"/v1/summary-views/{view_id}")
            resp.raise_for_status()
            return resp.json()
