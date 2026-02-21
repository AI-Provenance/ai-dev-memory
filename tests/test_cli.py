import pytest
from typer.testing import CliRunner
from devmemory.cli import app

runner = CliRunner()


class TestCLI:
    def test_cli_help(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "devmemory" in result.stdout.lower()

    def test_cli_no_args_shows_help(self):
        result = runner.invoke(app, [])
        assert result.exit_code in [0, 2]

    def test_status_command(self, temp_git_repo, monkeypatch):
        monkeypatch.chdir(temp_git_repo)
        result = runner.invoke(app, ["status"])
        assert result.exit_code in [0, 1]

    def test_search_command_requires_query(self):
        result = runner.invoke(app, ["search"])
        assert result.exit_code != 0

    def test_why_command_requires_filepath(self):
        result = runner.invoke(app, ["why"])
        assert result.exit_code != 0

    def test_sync_command_outside_git(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["sync", "--all"])
        assert result.exit_code in [0, 1]

    def test_config_commands(self):
        result = runner.invoke(app, ["config", "--help"])
        assert result.exit_code == 0

    def test_invalid_command(self):
        result = runner.invoke(app, ["nonexistent"])
        assert result.exit_code != 0

    def test_learn_command_help(self):
        result = runner.invoke(app, ["learn", "--help"])
        assert result.exit_code == 0

    def test_context_command_help(self):
        result = runner.invoke(app, ["context", "--help"])
        assert result.exit_code == 0

    def test_summarize_command_help(self):
        result = runner.invoke(app, ["summarize", "--help"])
        assert result.exit_code == 0

    def test_add_command_help(self):
        result = runner.invoke(app, ["add", "--help"])
        assert result.exit_code == 0

    def test_prompts_command_help(self):
        result = runner.invoke(app, ["prompts", "--help"])
        assert result.exit_code == 0


class TestCLISyncOptions:
    def test_sync_all_flag(self, temp_git_repo, monkeypatch):
        monkeypatch.chdir(temp_git_repo)
        result = runner.invoke(app, ["sync", "--all"])
        assert result.exit_code in [0, 1]

    def test_sync_latest_flag(self, temp_git_repo, monkeypatch):
        monkeypatch.chdir(temp_git_repo)
        result = runner.invoke(app, ["sync", "--latest"])
        assert result.exit_code in [0, 1]

    def test_sync_dry_run(self, temp_git_repo, monkeypatch):
        monkeypatch.chdir(temp_git_repo)
        result = runner.invoke(app, ["sync", "--all", "--dry-run"])
        assert result.exit_code in [0, 1]

    def test_sync_include_human(self, temp_git_repo, monkeypatch):
        monkeypatch.chdir(temp_git_repo)
        result = runner.invoke(app, ["sync", "--all", "--include-human"])
        assert result.exit_code in [0, 1]


class TestCLISearchOptions:
    def test_search_with_limit(self, temp_git_repo, monkeypatch):
        monkeypatch.chdir(temp_git_repo)
        result = runner.invoke(app, ["search", "test", "--limit", "5"])
        assert result.exit_code in [0, 1]

    def test_search_with_raw_flag(self, temp_git_repo, monkeypatch):
        monkeypatch.chdir(temp_git_repo)
        result = runner.invoke(app, ["search", "test", "--raw"])
        assert result.exit_code in [0, 1]

    def test_search_with_threshold(self, temp_git_repo, monkeypatch):
        monkeypatch.chdir(temp_git_repo)
        result = runner.invoke(app, ["search", "test", "--threshold", "0.5"])
        assert result.exit_code in [0, 1]


class TestCLIWhyCommand:
    def test_why_missing_file(self, temp_git_repo, monkeypatch):
        monkeypatch.chdir(temp_git_repo)
        result = runner.invoke(app, ["why", "nonexistent.py"])
        assert result.exit_code == 1

    def test_why_with_function(self, temp_git_repo, monkeypatch):
        monkeypatch.chdir(temp_git_repo)
        result = runner.invoke(app, ["why", "test.txt", "main"])
        assert result.exit_code in [0, 1]

    def test_why_raw_mode(self, temp_git_repo, monkeypatch):
        monkeypatch.chdir(temp_git_repo)
        result = runner.invoke(app, ["why", "test.txt", "--raw"])
        assert result.exit_code in [0, 1]
