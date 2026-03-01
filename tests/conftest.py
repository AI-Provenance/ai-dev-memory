import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
import subprocess
import os


@pytest.fixture
def temp_git_repo(tmp_path):
    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()
    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_path, check=True, capture_output=True)
    test_file = repo_path / "test.txt"
    test_file.write_text("initial content")
    subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_path, check=True, capture_output=True)
    return repo_path


@pytest.fixture
def temp_config_dir(tmp_path, monkeypatch):
    config_dir = tmp_path / ".devmemory"
    config_dir.mkdir()
    return config_dir


@pytest.fixture
def sample_commit_note():
    from devmemory.core.git_ai_parser import CommitNote, CommitStats

    return CommitNote(
        sha="abc123def456789",
        author_name="Test Author",
        author_email="test@test.com",
        subject="feat: add new feature",
        date="2026-02-21T10:00:00",
        has_ai_note=True,
        raw_note='{"prompts": []}',
        stats=CommitStats(ai_additions=10, human_additions=5),
        files=[],
        prompts={},
        body="Test commit body",
    )


@pytest.fixture
def mock_env_no_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
