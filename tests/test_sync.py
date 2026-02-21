import pytest
from unittest.mock import patch, MagicMock
import typer


class TestSyncCommand:
    def test_sync_no_git_repo(self, mock_ams_client, monkeypatch):
        with patch("devmemory.commands.sync.get_repo_root") as mock_get_root:
            mock_get_root.return_value = None

            from devmemory.commands.sync import run_sync

            with pytest.raises(typer.Exit) as exc_info:
                run_sync(all_commits=True)
            assert exc_info.value.exit_code == 1

    def test_sync_empty_notes(self, mock_ams_client, temp_git_repo, monkeypatch):
        monkeypatch.chdir(temp_git_repo)

        with patch("devmemory.commands.sync.get_ai_notes_since") as mock_notes:
            mock_notes.return_value = []

            from devmemory.commands.sync import run_sync

            with pytest.raises(typer.Exit) as exc_info:
                run_sync(all_commits=True)
            assert exc_info.value.exit_code == 0

    def test_sync_with_ai_notes(self, mock_ams_client, temp_git_repo, sample_commit_note, monkeypatch):
        monkeypatch.chdir(temp_git_repo)

        with patch("devmemory.commands.sync.get_ai_notes_since") as mock_notes:
            mock_notes.return_value = [sample_commit_note]
            with patch("devmemory.commands.sync.format_commit_as_memories") as mock_format:
                mock_format.return_value = [{"text": "test memory"}]
                with patch("devmemory.commands.sync.AMSClient") as mock_client_class:
                    mock_client_class.return_value = mock_ams_client

                    from devmemory.commands.sync import run_sync

                    run_sync(all_commits=True, quiet=True)

    def test_sync_dry_run(self, mock_ams_client, temp_git_repo, sample_commit_note, monkeypatch):
        monkeypatch.chdir(temp_git_repo)

        with patch("devmemory.commands.sync.get_ai_notes_since") as mock_notes:
            mock_notes.return_value = [sample_commit_note]
            with patch("devmemory.commands.sync.format_commit_as_memories") as mock_format:
                mock_format.return_value = [{"text": "test memory"}]

                from devmemory.commands.sync import run_sync

                with pytest.raises(typer.Exit) as exc_info:
                    run_sync(all_commits=True, dry_run=True)

                assert exc_info.value.exit_code == 0
                mock_ams_client.create_memories.assert_not_called()

    def test_sync_ams_unreachable(self, temp_git_repo, sample_commit_note, monkeypatch):
        monkeypatch.chdir(temp_git_repo)

        with patch("devmemory.commands.sync.get_ai_notes_since") as mock_notes:
            mock_notes.return_value = [sample_commit_note]

            with patch("devmemory.commands.sync.AMSClient") as mock_client_class:
                mock_client = MagicMock()
                mock_client.health_check.side_effect = Exception("Connection refused")
                mock_client_class.return_value = mock_client

                from devmemory.commands.sync import run_sync

                with pytest.raises(typer.Exit) as exc_info:
                    run_sync(all_commits=True)
                assert exc_info.value.exit_code == 1

    def test_sync_handles_empty_notes_to_sync(self, temp_git_repo, monkeypatch):
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

            from devmemory.commands.sync import run_sync

            with pytest.raises(typer.Exit) as exc_info:
                run_sync(all_commits=True, ai_only=True)
            assert exc_info.value.exit_code == 0

    def test_sync_latest_commit(self, mock_ams_client, temp_git_repo, sample_commit_note, monkeypatch):
        monkeypatch.chdir(temp_git_repo)

        with patch("devmemory.commands.sync.get_latest_commit_note") as mock_latest:
            mock_latest.return_value = sample_commit_note
            with patch("devmemory.commands.sync.format_commit_as_memories") as mock_format:
                mock_format.return_value = [{"text": "test memory"}]
                with patch("devmemory.commands.sync.AMSClient") as mock_client_class:
                    mock_client_class.return_value = mock_ams_client

                    from devmemory.commands.sync import run_sync

                    run_sync(latest=True, quiet=True)

    def test_sync_latest_no_commits(self, mock_ams_client, temp_git_repo, monkeypatch):
        monkeypatch.chdir(temp_git_repo)

        with patch("devmemory.commands.sync.get_latest_commit_note") as mock_latest:
            mock_latest.return_value = None

            from devmemory.commands.sync import run_sync

            with pytest.raises(typer.Exit) as exc_info:
                run_sync(latest=True)
            assert exc_info.value.exit_code == 0
