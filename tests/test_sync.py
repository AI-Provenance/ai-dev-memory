import pytest
from unittest.mock import patch, MagicMock
import typer


class TestSyncCommand:
    def test_sync_no_git_repo(self, monkeypatch):
        with patch("devmemory.commands.sync.get_repo_root") as mock_get_root:
            mock_get_root.return_value = None

            from devmemory.commands.sync import run_sync

            with pytest.raises(typer.Exit) as exc_info:
                run_sync(all_commits=True)
            assert exc_info.value.exit_code == 1

    def test_sync_dry_run(self, temp_git_repo, sample_commit_note, monkeypatch):
        """Test dry run mode doesn't write anything."""
        monkeypatch.chdir(temp_git_repo)

        with patch("devmemory.commands.sync.get_ai_notes_since") as mock_notes:
            mock_notes.return_value = [sample_commit_note]
            with patch("devmemory.commands.sync.DevMemoryConfig") as mock_config_class:
                mock_config = MagicMock()
                mock_config.is_local_mode.return_value = True
                mock_config.get_sqlite_path.return_value = str(temp_git_repo / ".devmemory" / "attributions.db")
                mock_config.get_active_namespace.return_value = "test"
                mock_config_class.load.return_value = mock_config

                from devmemory.commands.sync import run_sync

                with pytest.raises(typer.Exit) as exc_info:
                    run_sync(all_commits=True, dry_run=True)

                assert exc_info.value.exit_code == 0

    def test_sync_handles_empty_notes_to_sync(self, temp_git_repo, monkeypatch):
        """Test handling notes without AI content."""
        monkeypatch.chdir(temp_git_repo)

        from devmemory.core.git_ai_parser import CommitNote

        note_without_ai = CommitNote(
            sha="abc123",
            author_name="Test",
            author_email="test@test.com",
            subject="test",
            date="2026-02-21",
            has_ai_note=False,
        )

        with patch("devmemory.commands.sync.get_ai_notes_since") as mock_notes:
            mock_notes.return_value = [note_without_ai]
            with patch("devmemory.commands.sync.DevMemoryConfig") as mock_config_class:
                mock_config = MagicMock()
                mock_config.is_local_mode.return_value = True
                mock_config.get_sqlite_path.return_value = str(temp_git_repo / ".devmemory" / "attributions.db")
                mock_config.get_active_namespace.return_value = "test"
                mock_config_class.load.return_value = mock_config

                from devmemory.commands.sync import run_sync

                with pytest.raises(typer.Exit) as exc_info:
                    run_sync(all_commits=True, ai_only=True)
                assert exc_info.value.exit_code == 0

    def test_sync_latest_no_commits(self, temp_git_repo, monkeypatch):
        """Test sync with no commits to sync."""
        monkeypatch.chdir(temp_git_repo)

        with patch("devmemory.commands.sync.get_latest_commit_note") as mock_latest:
            mock_latest.return_value = None

            from devmemory.commands.sync import run_sync

            with pytest.raises(typer.Exit) as exc_info:
                run_sync(latest=True)
            assert exc_info.value.exit_code == 0

    def test_sync_empty_notes(self, temp_git_repo, monkeypatch):
        """Test sync with empty notes list."""
        monkeypatch.chdir(temp_git_repo)

        with patch("devmemory.commands.sync.get_ai_notes_since") as mock_notes:
            mock_notes.return_value = []

            from devmemory.commands.sync import run_sync

            with pytest.raises(typer.Exit) as exc_info:
                run_sync(all_commits=True)
            assert exc_info.value.exit_code == 0
