import os
from pathlib import Path

from devmemory.core import llm_client


def test_find_env_file_prefers_project_env(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    (project / ".git").mkdir()
    env_path = project / ".env"
    env_path.write_text("OPENAI_API_KEY=fake\n")
    monkeypatch.chdir(project)
    found = llm_client._find_env_file()
    assert found == env_path
    parsed = llm_client._parse_env_file(found)
    assert parsed["OPENAI_API_KEY"] == "fake"


def test_synthesize_answer_raises_without_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    cwd = Path.cwd()
    env = cwd / ".env"
    if env.exists():
        text = env.read_text()
        env.rename(cwd / ".env.backup")
    try:
        try:
            llm_client.synthesize_answer("q", [])
        except llm_client.LLMError as e:
            assert "no_api_key" in str(e)
        else:
            assert False
    finally:
        backup = cwd / ".env.backup"
        if backup.exists():
            backup.rename(cwd / ".env")

