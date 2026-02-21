import pytest
from unittest.mock import patch, MagicMock


class TestSearchCommand:
    def test_search_empty_results(self, mock_ams_client, temp_git_repo, monkeypatch):
        monkeypatch.chdir(temp_git_repo)
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        mock_ams_client.search_memories.return_value = []

        from devmemory.commands.search import run_search

        run_search(query="nonexistent query", raw=True)

    def test_search_with_results(self, mock_ams_client, temp_git_repo, sample_memory_result, monkeypatch):
        monkeypatch.chdir(temp_git_repo)
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        mock_ams_client.search_memories.return_value = [sample_memory_result]

        from devmemory.commands.search import run_search

        run_search(query="authentication", raw=True)

    def test_search_threshold_filtering(self, mock_ams_client, temp_git_repo, monkeypatch):
        monkeypatch.chdir(temp_git_repo)
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        from devmemory.core.ams_client import MemoryResult

        low_relevance = MemoryResult(
            id="low-id",
            text="Low relevance result",
            score=0.95,
            topics=[],
            entities=[],
            memory_type="semantic",
            created_at="2026-02-21",
        )
        high_relevance = MemoryResult(
            id="high-id",
            text="High relevance result",
            score=0.15,
            topics=[],
            entities=[],
            memory_type="semantic",
            created_at="2026-02-21",
        )
        mock_ams_client.search_memories.return_value = [low_relevance, high_relevance]

        from devmemory.commands.search import run_search

        run_search(query="test", threshold=0.75, raw=True)

    def test_search_with_namespace_filter(self, mock_ams_client, temp_git_repo, sample_memory_result, monkeypatch):
        monkeypatch.chdir(temp_git_repo)
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        mock_ams_client.search_memories.return_value = [sample_memory_result]

        from devmemory.commands.search import run_search

        run_search(query="test", namespace="custom-namespace", raw=True)

    def test_search_with_memory_type_filter(self, mock_ams_client, temp_git_repo, sample_memory_result, monkeypatch):
        monkeypatch.chdir(temp_git_repo)
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        mock_ams_client.search_memories.return_value = [sample_memory_result]

        from devmemory.commands.search import run_search

        run_search(query="test", memory_type="episodic", raw=True)

    def test_search_no_git_repo(self, mock_ams_client, monkeypatch):
        monkeypatch.setattr("devmemory.core.utils.get_repo_root", lambda: None)

        from devmemory.commands.search import run_search

        run_search(query="test", raw=True)

    def test_search_ams_unreachable(self, temp_git_repo, monkeypatch):
        monkeypatch.chdir(temp_git_repo)
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        with patch("devmemory.core.ams_client.AMSClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.search_memories.side_effect = Exception("Connection refused")
            mock_client_class.return_value = mock_client

            from devmemory.commands.search import run_search

            run_search(query="test", raw=True)
