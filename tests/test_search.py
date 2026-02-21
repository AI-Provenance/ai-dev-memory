import pytest
from unittest.mock import patch, MagicMock
import typer


class TestSearchCommand:
    def test_search_empty_results(self, temp_git_repo, sample_memory_result, monkeypatch):
        monkeypatch.chdir(temp_git_repo)
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        mock_client = MagicMock()
        mock_client.health_check.return_value = {"status": "ok"}
        mock_client.search_memories.return_value = []

        with patch("devmemory.commands.search.AMSClient", return_value=mock_client):
            from devmemory.commands.search import run_search

            with pytest.raises(typer.Exit) as exc_info:
                run_search(query="nonexistent query", raw=True)
            assert exc_info.value.exit_code == 0

    def test_search_with_results(self, temp_git_repo, sample_memory_result, monkeypatch):
        monkeypatch.chdir(temp_git_repo)
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        mock_client = MagicMock()
        mock_client.health_check.return_value = {"status": "ok"}
        mock_client.search_memories.return_value = [sample_memory_result]

        with patch("devmemory.commands.search.AMSClient", return_value=mock_client):
            from devmemory.commands.search import run_search

            run_search(query="authentication", raw=True)

    def test_search_threshold_filtering(self, temp_git_repo, monkeypatch):
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

        mock_client = MagicMock()
        mock_client.health_check.return_value = {"status": "ok"}
        mock_client.search_memories.return_value = [low_relevance, high_relevance]

        with patch("devmemory.commands.search.AMSClient", return_value=mock_client):
            from devmemory.commands.search import run_search

            run_search(query="test", threshold=0.75, raw=True)

    def test_search_with_namespace_filter(self, temp_git_repo, sample_memory_result, monkeypatch):
        monkeypatch.chdir(temp_git_repo)
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        mock_client = MagicMock()
        mock_client.health_check.return_value = {"status": "ok"}
        mock_client.search_memories.return_value = [sample_memory_result]

        with patch("devmemory.commands.search.AMSClient", return_value=mock_client):
            from devmemory.commands.search import run_search

            run_search(query="test", namespace="custom-namespace", raw=True)

    def test_search_with_memory_type_filter(self, temp_git_repo, sample_memory_result, monkeypatch):
        monkeypatch.chdir(temp_git_repo)
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        mock_client = MagicMock()
        mock_client.health_check.return_value = {"status": "ok"}
        mock_client.search_memories.return_value = [sample_memory_result]

        with patch("devmemory.commands.search.AMSClient", return_value=mock_client):
            from devmemory.commands.search import run_search

            run_search(query="test", memory_type="episodic", raw=True)

    def test_search_no_git_repo(self, monkeypatch):
        mock_client = MagicMock()
        mock_client.health_check.return_value = {"status": "ok"}
        mock_client.search_memories.return_value = []

        with patch("devmemory.commands.search.AMSClient", return_value=mock_client):
            from devmemory.commands.search import run_search

            with pytest.raises(typer.Exit) as exc_info:
                run_search(query="test", raw=True)
            assert exc_info.value.exit_code == 0

    def test_search_ams_unreachable(self, temp_git_repo, monkeypatch):
        monkeypatch.chdir(temp_git_repo)
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        mock_client = MagicMock()
        mock_client.health_check.side_effect = Exception("Connection refused")

        with patch("devmemory.commands.search.AMSClient", return_value=mock_client):
            from devmemory.commands.search import run_search

            with pytest.raises(typer.Exit) as exc_info:
                run_search(query="test", raw=True)
            assert exc_info.value.exit_code == 1
