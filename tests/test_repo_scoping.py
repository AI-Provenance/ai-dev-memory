import os
import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from devmemory.core.config import DevMemoryConfig
from devmemory.core.utils import get_repo_id, get_repo_root


def test_repo_id_generation():
    with patch("devmemory.core.utils.get_repo_root") as mock_root:
        mock_root.return_value = "/tmp/repo-a"
        with patch("subprocess.run") as mock_run:
            # Mock git remote origin URL
            mock_run.return_value = MagicMock(stdout="https://github.com/user/repo-a.git\n")
            repo_id = get_repo_id.__wrapped__()  # Use __wrapped__ because of lru_cache
            assert "github-com-user-repo-a" in repo_id


def test_config_active_namespace():
    config = DevMemoryConfig(namespace="test-ns")
    with patch("devmemory.core.config.get_repo_id") as mock_id:
        mock_id.return_value = "repo-abc"
        assert config.get_active_namespace() == "test-ns:repo-abc"

        mock_id.return_value = "non-git"
        assert config.get_active_namespace() == "test-ns"
