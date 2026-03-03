import pytest
from typer.testing import CliRunner
from devmemory.cli import app
from unittest.mock import MagicMock, patch
import sqlite3

runner = CliRunner()


@pytest.fixture
def mock_sqlite_storage():
    """Mock SQLiteAttributionStorage for testing."""
    mock_storage = MagicMock()
    mock_conn = MagicMock()
    mock_storage._get_conn.return_value = mock_conn
    mock_storage.close = MagicMock()
    return mock_storage, mock_conn


class TestAttributionList:
    """Tests for 'devmemory attribution list' command."""

    def test_list_shows_table_format(self, temp_git_repo, monkeypatch, mock_sqlite_storage):
        """Test that list command outputs a table with expected columns."""
        monkeypatch.chdir(temp_git_repo)
        mock_storage, mock_conn = mock_sqlite_storage

        # Mock database response
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            ("src/main.py", "abc123def456"),
            ("src/utils.py", "def456abc123"),
        ]
        mock_cursor.fetchone.return_value = ("ai",)
        mock_conn.execute.return_value = mock_cursor

        with patch("devmemory.commands.attribution._get_storage", return_value=(mock_storage, "sqlite")):
            with patch("devmemory.commands.attribution._get_namespace", return_value="test-ns"):
                result = runner.invoke(app, ["attribution", "list"])

        assert result.exit_code == 0
        # Check for table headers
        assert "File" in result.stdout
        assert "Commit" in result.stdout
        assert "Author" in result.stdout
        # Check for data
        assert "src/main.py" in result.stdout
        assert "src/utils.py" in result.stdout

    def test_list_shows_no_attributions_message(self, temp_git_repo, monkeypatch, mock_sqlite_storage):
        """Test that list shows proper message when no attributions found."""
        monkeypatch.chdir(temp_git_repo)
        mock_storage, mock_conn = mock_sqlite_storage

        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_conn.execute.return_value = mock_cursor

        with patch("devmemory.commands.attribution._get_storage", return_value=(mock_storage, "sqlite")):
            with patch("devmemory.commands.attribution._get_namespace", return_value="test-ns"):
                result = runner.invoke(app, ["attribution", "list"])

        assert result.exit_code == 0
        assert "No attributions found" in result.stdout
        assert "Hint: run devmemory sync first" in result.stdout

    def test_list_with_limit_option(self, temp_git_repo, monkeypatch, mock_sqlite_storage):
        """Test that limit option is respected."""
        monkeypatch.chdir(temp_git_repo)
        mock_storage, mock_conn = mock_sqlite_storage

        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_conn.execute.return_value = mock_cursor

        with patch("devmemory.commands.attribution._get_storage", return_value=(mock_storage, "sqlite")):
            with patch("devmemory.commands.attribution._get_namespace", return_value="test-ns"):
                result = runner.invoke(app, ["attribution", "list", "--limit", "10"])

        assert result.exit_code == 0


class TestAttributionShow:
    """Tests for 'devmemory attribution show' command."""

    def test_show_displays_line_attributions_table(self, temp_git_repo, monkeypatch, mock_sqlite_storage):
        """Test that show command outputs line attributions in table format."""
        monkeypatch.chdir(temp_git_repo)
        mock_storage, mock_conn = mock_sqlite_storage

        # Mock file_latest lookup
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = ("abc123def456",)

        # Mock attribution data
        mock_cursor.fetchall.return_value = [
            (10, 20, "ai", "opencode", "opencode/trinity-large", "7a66807c780f"),
            (25, 30, "human", "-", "-", None),
        ]
        mock_conn.execute.return_value = mock_cursor

        with patch("devmemory.commands.attribution._get_storage", return_value=(mock_storage, "sqlite")):
            with patch("devmemory.commands.attribution._get_namespace", return_value="test-ns"):
                result = runner.invoke(app, ["attribution", "show", "src/main.py"])

        assert result.exit_code == 0
        # Check for headers
        assert "File:" in result.stdout
        assert "Namespace:" in result.stdout
        assert "Commit:" in result.stdout
        assert "Line Attribution" in result.stdout
        # Check for table columns
        assert "Lines" in result.stdout
        assert "Author" in result.stdout
        assert "Tool" in result.stdout
        assert "Model" in result.stdout
        assert "Prompt ID" in result.stdout

    def test_show_displays_correct_line_ranges(self, temp_git_repo, monkeypatch, mock_sqlite_storage):
        """Test that line ranges are displayed correctly (single vs range)."""
        monkeypatch.chdir(temp_git_repo)
        mock_storage, mock_conn = mock_sqlite_storage

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = ("abc123",)
        mock_cursor.fetchall.return_value = [
            (10, 10, "ai", "tool", "model", "pid"),  # Single line
            (20, 25, "ai", "tool", "model", "pid"),  # Range
        ]
        mock_conn.execute.return_value = mock_cursor

        with patch("devmemory.commands.attribution._get_storage", return_value=(mock_storage, "sqlite")):
            with patch("devmemory.commands.attribution._get_namespace", return_value="test-ns"):
                result = runner.invoke(app, ["attribution", "show", "test.py"])

        assert result.exit_code == 0
        # Single line should show as "10", range as "20-25"
        assert "10" in result.stdout
        assert "20-25" in result.stdout

    def test_show_file_not_found_error(self, temp_git_repo, monkeypatch, mock_sqlite_storage):
        """Test that show command displays error when file not found."""
        monkeypatch.chdir(temp_git_repo)
        mock_storage, mock_conn = mock_sqlite_storage

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.execute.return_value = mock_cursor

        with patch("devmemory.commands.attribution._get_storage", return_value=(mock_storage, "sqlite")):
            with patch("devmemory.commands.attribution._get_namespace", return_value="test-ns"):
                result = runner.invoke(app, ["attribution", "show", "nonexistent.py"])

        assert result.exit_code == 1
        assert "No attribution found" in result.stdout


class TestAttributionLookup:
    """Tests for 'devmemory attribution lookup' command."""

    def test_lookup_displays_attribution_info(self, temp_git_repo, monkeypatch, mock_sqlite_storage):
        """Test that lookup shows all attribution fields."""
        monkeypatch.chdir(temp_git_repo)
        mock_storage, mock_conn = mock_sqlite_storage

        mock_storage.get_latest_attribution.return_value = {
            "commit_sha": "abc123def456",
            "author": "ai",
            "tool": "opencode",
            "model": "opencode/trinity-large",
            "prompt_id": "7a66807c780ff9f0",
            "author_email": "test@example.com",
            "confidence": 0.95,
        }

        with patch("devmemory.commands.attribution._get_storage", return_value=(mock_storage, "sqlite")):
            with patch("devmemory.commands.attribution._get_namespace", return_value="test-ns"):
                result = runner.invoke(app, ["attribution", "lookup", "src/main.py", "10"])

        assert result.exit_code == 0
        # Check for all expected fields
        assert "File:" in result.stdout
        assert "Line:" in result.stdout
        assert "Namespace:" in result.stdout
        assert "Commit:" in result.stdout
        assert "AI-generated" in result.stdout
        assert "Tool:" in result.stdout
        assert "Model:" in result.stdout
        assert "Prompt ID:" in result.stdout
        assert "Author:" in result.stdout
        assert "Confidence:" in result.stdout

    def test_lookup_shows_human_written_for_non_ai(self, temp_git_repo, monkeypatch, mock_sqlite_storage):
        """Test that lookup shows 'Human-written' for non-AI code."""
        monkeypatch.chdir(temp_git_repo)
        mock_storage, mock_conn = mock_sqlite_storage

        mock_storage.get_latest_attribution.return_value = {
            "commit_sha": "abc123",
            "author": "human",
            "confidence": 0.95,
        }

        with patch("devmemory.commands.attribution._get_storage", return_value=(mock_storage, "sqlite")):
            with patch("devmemory.commands.attribution._get_namespace", return_value="test-ns"):
                result = runner.invoke(app, ["attribution", "lookup", "src/main.py", "10"])

        assert result.exit_code == 0
        assert "Human-written" in result.stdout

    def test_lookup_not_found_error(self, temp_git_repo, monkeypatch, mock_sqlite_storage):
        """Test that lookup shows error when attribution not found."""
        monkeypatch.chdir(temp_git_repo)
        mock_storage, mock_conn = mock_sqlite_storage

        mock_storage.get_latest_attribution.return_value = None

        with patch("devmemory.commands.attribution._get_storage", return_value=(mock_storage, "sqlite")):
            with patch("devmemory.commands.attribution._get_namespace", return_value="test-ns"):
                result = runner.invoke(app, ["attribution", "lookup", "test.py", "999"])

        assert result.exit_code == 1
        assert "No attribution found" in result.stdout

    def test_lookup_with_commit_sha(self, temp_git_repo, monkeypatch, mock_sqlite_storage):
        """Test that lookup with explicit commit SHA uses get_attribution."""
        monkeypatch.chdir(temp_git_repo)
        mock_storage, mock_conn = mock_sqlite_storage

        mock_storage.get_attribution.return_value = {
            "commit_sha": "specific123",
            "author": "ai",
            "confidence": 0.95,
        }

        with patch("devmemory.commands.attribution._get_storage", return_value=(mock_storage, "sqlite")):
            with patch("devmemory.commands.attribution._get_namespace", return_value="test-ns"):
                result = runner.invoke(app, ["attribution", "lookup", "test.py", "10", "specific123"])

        assert result.exit_code == 0
        mock_storage.get_attribution.assert_called_once()


class TestAttributionLookupWithDiff:
    """Tests for 'devmemory attribution lookup --diff' command."""

    def test_lookup_diff_shows_git_diff(self, temp_git_repo, monkeypatch, mock_sqlite_storage):
        """Test that --diff flag shows git diff output."""
        monkeypatch.chdir(temp_git_repo)
        mock_storage, mock_conn = mock_sqlite_storage

        mock_storage.get_latest_attribution.return_value = {
            "commit_sha": "abc123",
            "author": "ai",
            "tool": "opencode",
            "model": "model",
            "confidence": 0.95,
        }

        with patch("devmemory.commands.attribution._get_storage", return_value=(mock_storage, "sqlite")):
            with patch("devmemory.commands.attribution._get_namespace", return_value="test-ns"):
                with patch("devmemory.commands.attribution._get_blame_commit", return_value="abc123"):
                    with patch(
                        "devmemory.commands.attribution._get_line_diff",
                        return_value="diff --git a/test.py\n+++ b/test.py\n@@ -1,1 +1,1 @@\n-old\n+new",
                    ):
                        with patch(
                            "devmemory.commands.attribution._highlight_line_in_diff",
                            return_value="diff --git a/test.py\n+++ b/test.py\n@@ -1,1 +1,1 @@\n-old\n>>> +new  <-- TARGET LINE",
                        ):
                            result = runner.invoke(app, ["attribution", "lookup", "test.py", "10", "--diff"])

        assert result.exit_code == 0
        assert "Git Diff for Line" in result.stdout
        assert "Commit that modified line" in result.stdout

    def test_lookup_diff_uses_git_ai_blame(self, temp_git_repo, monkeypatch, mock_sqlite_storage):
        """Test that --diff uses git-ai blame instead of regular git blame."""
        monkeypatch.chdir(temp_git_repo)
        mock_storage, mock_conn = mock_sqlite_storage

        mock_storage.get_latest_attribution.return_value = {
            "commit_sha": "abc123",
            "author": "ai",
            "confidence": 0.95,
        }

        with patch("devmemory.commands.attribution._get_storage", return_value=(mock_storage, "sqlite")):
            with patch("devmemory.commands.attribution._get_namespace", return_value="test-ns"):
                with patch("devmemory.commands.attribution._get_blame_commit") as mock_blame:
                    with patch("devmemory.commands.attribution._get_line_diff", return_value="diff"):
                        with patch("devmemory.commands.attribution._highlight_line_in_diff", return_value="diff"):
                            mock_blame.return_value = "abc123"
                            result = runner.invoke(app, ["attribution", "lookup", "test.py", "10", "--diff"])

        assert result.exit_code == 0
        mock_blame.assert_called_once_with("test.py", 10)

    def test_lookup_diff_handles_no_commit(self, temp_git_repo, monkeypatch, mock_sqlite_storage):
        """Test that --diff handles case when commit cannot be determined."""
        monkeypatch.chdir(temp_git_repo)
        mock_storage, mock_conn = mock_sqlite_storage

        mock_storage.get_latest_attribution.return_value = {
            "commit_sha": "abc123",
            "author": "ai",
            "confidence": 0.95,
        }

        with patch("devmemory.commands.attribution._get_storage", return_value=(mock_storage, "sqlite")):
            with patch("devmemory.commands.attribution._get_namespace", return_value="test-ns"):
                with patch("devmemory.commands.attribution._get_blame_commit", return_value=None):
                    result = runner.invoke(app, ["attribution", "lookup", "test.py", "10", "--diff"])

        assert result.exit_code == 0
        assert "Could not determine commit" in result.stdout


class TestAttributionHistory:
    """Tests for 'devmemory attribution history' command."""

    def test_history_shows_commit_list(self, temp_git_repo, monkeypatch, mock_sqlite_storage):
        """Test that history command shows list of commits."""
        monkeypatch.chdir(temp_git_repo)
        mock_storage, mock_conn = mock_sqlite_storage

        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            ("abc123", 1772193750),
            ("def456", 1772193760),
        ]
        mock_cursor.fetchone.return_value = (5,)  # range count
        mock_conn.execute.return_value = mock_cursor

        with patch("devmemory.commands.attribution._get_storage", return_value=(mock_storage, "sqlite")):
            with patch("devmemory.commands.attribution._get_namespace", return_value="test-ns"):
                result = runner.invoke(app, ["attribution", "history", "src/main.py"])

        assert result.exit_code == 0
        assert "File:" in result.stdout
        assert "Namespace:" in result.stdout
        assert "Attribution History" in result.stdout
        assert "Commit" in result.stdout
        assert "Date" in result.stdout
        assert "AI Blocks" in result.stdout

    def test_history_no_data_message(self, temp_git_repo, monkeypatch, mock_sqlite_storage):
        """Test that history shows message when no data found."""
        monkeypatch.chdir(temp_git_repo)
        mock_storage, mock_conn = mock_sqlite_storage

        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_conn.execute.return_value = mock_cursor

        with patch("devmemory.commands.attribution._get_storage", return_value=(mock_storage, "sqlite")):
            with patch("devmemory.commands.attribution._get_namespace", return_value="test-ns"):
                result = runner.invoke(app, ["attribution", "history", "nonexistent.py"])

        assert result.exit_code == 0
        assert "No attribution data found" in result.stdout


class TestAttributionOutputFormat:
    """Tests to ensure CLI output format remains consistent."""

    def test_list_output_structure(self, temp_git_repo, monkeypatch, mock_sqlite_storage):
        """Test that list output has consistent structure."""
        monkeypatch.chdir(temp_git_repo)
        mock_storage, mock_conn = mock_sqlite_storage

        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [("file.py", "abc123")]
        mock_cursor.fetchone.return_value = ("ai",)
        mock_conn.execute.return_value = mock_cursor

        with patch("devmemory.commands.attribution._get_storage", return_value=(mock_storage, "sqlite")):
            with patch("devmemory.commands.attribution._get_namespace", return_value="test-ns"):
                result = runner.invoke(app, ["attribution", "list"])

        # Check for expected sections
        assert "Attributions in" in result.stdout
        assert "files)" in result.stdout
        assert "Showing" in result.stdout

    def test_show_output_structure(self, temp_git_repo, monkeypatch, mock_sqlite_storage):
        """Test that show output has consistent structure."""
        monkeypatch.chdir(temp_git_repo)
        mock_storage, mock_conn = mock_sqlite_storage

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = ("abc123",)
        mock_cursor.fetchall.return_value = [(1, 10, "ai", "tool", "model", "pid")]
        mock_conn.execute.return_value = mock_cursor

        with patch("devmemory.commands.attribution._get_storage", return_value=(mock_storage, "sqlite")):
            with patch("devmemory.commands.attribution._get_namespace", return_value="test-ns"):
                result = runner.invoke(app, ["attribution", "show", "test.py"])

        # Check for bold labels (Rich format)
        assert "File:" in result.stdout
        assert "Namespace:" in result.stdout
        assert "Commit:" in result.stdout

    def test_lookup_output_structure(self, temp_git_repo, monkeypatch, mock_sqlite_storage):
        """Test that lookup output has consistent structure."""
        monkeypatch.chdir(temp_git_repo)
        mock_storage, mock_conn = mock_sqlite_storage

        mock_storage.get_latest_attribution.return_value = {
            "commit_sha": "abc123",
            "author": "ai",
            "tool": "tool",
            "model": "model",
            "prompt_id": "pid",
            "author_email": "email@test.com",
            "confidence": 0.95,
        }

        with patch("devmemory.commands.attribution._get_storage", return_value=(mock_storage, "sqlite")):
            with patch("devmemory.commands.attribution._get_namespace", return_value="test-ns"):
                result = runner.invoke(app, ["attribution", "lookup", "test.py", "1"])

        # Check for all expected labels
        assert "File:" in result.stdout
        assert "Line:" in result.stdout
        assert "Namespace:" in result.stdout
        assert "Commit:" in result.stdout
        assert "Tool:" in result.stdout
        assert "Model:" in result.stdout
        assert "Prompt ID:" in result.stdout
        assert "Author:" in result.stdout
        assert "Confidence:" in result.stdout
