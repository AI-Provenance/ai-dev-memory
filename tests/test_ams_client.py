import pytest
from unittest.mock import patch, MagicMock, PropertyMock
import httpx


class TestAMSClientInit:
    def test_init_default_values(self):
        from devmemory.core.ams_client import AMSClient

        client = AMSClient()
        assert client.base_url == "http://localhost:8000"
        assert client.timeout == 30.0
        assert client._shared_client is None

    def test_init_custom_values(self):
        from devmemory.core.ams_client import AMSClient

        client = AMSClient(base_url="http://custom:9000/", timeout=60.0)
        assert client.base_url == "http://custom:9000"
        assert client.timeout == 60.0


class TestAMSClientContextManager:
    def test_context_manager_creates_client(self):
        from devmemory.core.ams_client import AMSClient

        with AMSClient() as client:
            assert client._shared_client is not None
        assert client._shared_client is None

    def test_context_manager_reuse(self):
        from devmemory.core.ams_client import AMSClient

        client = AMSClient()
        with client:
            assert client._shared_client is not None
        assert client._shared_client is None


class TestAMSClientCreateMemories:
    def test_create_memories_empty_list(self):
        from devmemory.core.ams_client import AMSClient

        client = AMSClient()
        result = client.create_memories([])
        assert result == {"count": 0, "ids": []}

    def test_create_memories_success(self):
        from devmemory.core.ams_client import AMSClient

        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.json.return_value = {"count": 2, "ids": ["id1", "id2"]}
            mock_client.post.return_value = mock_response
            mock_client_class.return_value = mock_client

            client = AMSClient()
            with patch.object(client, "_get_client", return_value=mock_client):
                result = client.create_memories([{"text": "memory 1"}, {"text": "memory 2"}])
                assert result["count"] == 2
                mock_client.post.assert_called_once()

    def test_create_memories_http_error(self):
        from devmemory.core.ams_client import AMSClient

        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.text = "Internal Server Error"
            mock_client.post.side_effect = httpx.HTTPStatusError(
                "Server error", request=MagicMock(), response=mock_response
            )
            mock_client_class.return_value = mock_client

            client = AMSClient()
            with patch.object(client, "_get_client", return_value=mock_client):
                with pytest.raises(httpx.HTTPStatusError):
                    client.create_memories([{"text": "test"}])


class TestAMSClientSearchMemories:
    def test_search_memories_success(self):
        from devmemory.core.ams_client import AMSClient, MemoryResult

        with patch.object(AMSClient, "_client_context") as mock_ctx:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "memories": [
                    {
                        "id": "mem-1",
                        "text": "test memory",
                        "dist": 0.1,
                        "topics": ["test"],
                        "entities": [],
                        "memory_type": "semantic",
                        "created_at": "2026-02-21T10:00:00",
                    }
                ]
            }
            mock_client.post.return_value = mock_response
            mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            client = AMSClient()
            results = client.search_memories("test query")
            assert len(results) == 1
            assert results[0].text == "test memory"
            assert results[0].score == 0.1

    def test_search_memories_empty_results(self):
        from devmemory.core.ams_client import AMSClient

        with patch.object(AMSClient, "_client_context") as mock_ctx:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.json.return_value = {"memories": []}
            mock_client.post.return_value = mock_response
            mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            client = AMSClient()
            results = client.search_memories("nonexistent")
            assert results == []

    def test_search_memories_with_filters(self):
        from devmemory.core.ams_client import AMSClient

        with patch.object(AMSClient, "_client_context") as mock_ctx:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.json.return_value = {"memories": []}
            mock_client.post.return_value = mock_response
            mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            client = AMSClient()
            client.search_memories(
                "test", limit=5, namespace="test-ns", user_id="user-1", topics=["topic1"], memory_type="episodic"
            )
            call_args = mock_client.post.call_args
            payload = call_args[1]["json"]
            assert payload["limit"] == 5
            assert payload["namespace"] == {"eq": "test-ns"}
            assert payload["user_id"] == {"eq": "user-1"}
            assert payload["topics"] == {"any": ["topic1"]}
            assert payload["memory_type"] == {"eq": "episodic"}


class TestAMSClientHealthCheck:
    def test_health_check_success(self):
        from devmemory.core.ams_client import AMSClient

        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.json.return_value = {"status": "ok"}
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            client = AMSClient()
            with patch.object(client, "_get_client", return_value=mock_client):
                result = client.health_check()
                assert result["status"] == "ok"

    def test_health_check_failure(self):
        from devmemory.core.ams_client import AMSClient

        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.status_code = 503
            mock_client.get.side_effect = httpx.HTTPStatusError(
                "Service unavailable", request=MagicMock(), response=mock_response
            )
            mock_client_class.return_value = mock_client

            client = AMSClient()
            with patch.object(client, "_get_client", return_value=mock_client):
                with pytest.raises(httpx.HTTPStatusError):
                    client.health_check()


class TestAMSClientGetMemoryCount:
    def test_get_memory_count_success(self):
        from devmemory.core.ams_client import AMSClient

        with patch.object(AMSClient, "_client_context") as mock_ctx:
            mock_client = MagicMock()
            mock_responses = [
                MagicMock(json=MagicMock(return_value={"memories": list(range(100)), "next_offset": 100})),
                MagicMock(json=MagicMock(return_value={"memories": list(range(50)), "next_offset": None})),
            ]
            mock_client.post.side_effect = mock_responses
            mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            client = AMSClient()
            count = client.get_memory_count()
            assert count == 150

    def test_get_memory_count_error(self):
        from devmemory.core.ams_client import AMSClient

        with patch.object(AMSClient, "_client_context") as mock_ctx:
            mock_client = MagicMock()
            mock_client.post.side_effect = Exception("Connection error")
            mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            client = AMSClient()
            count = client.get_memory_count()
            assert count == -1
