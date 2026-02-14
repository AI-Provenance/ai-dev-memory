import subprocess

import pytest
from click.exceptions import Exit as ClickExit

from devmemory.commands import why
from devmemory.commands.why import (
    _build_query,
    _get_git_blame_summary,
    _get_git_log_for_file,
    WHY_SYSTEM_PROMPT,
)


# ── _build_query ────────────────────────────────────────────────────────────────


def test_build_query_file_only():
    q = _build_query("src/auth.py")
    assert "src/auth.py" in q
    assert "implementation" in q
    assert "history" in q


def test_build_query_with_function():
    q = _build_query("src/auth.py", "login")
    assert "src/auth.py" in q
    assert "login" in q
    assert "implementation" in q


# ── _get_git_log_for_file ───────────────────────────────────────────────────────


def test_get_git_log_returns_stdout(monkeypatch):
    fake_output = "abc123|Alice|feat: add auth|2026-01-01T00:00:00+00:00"

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout=fake_output, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = _get_git_log_for_file("src/auth.py")
    assert "abc123" in result
    assert "Alice" in result


def test_get_git_log_returns_empty_on_error(monkeypatch):
    def fake_run(cmd, **kwargs):
        raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = _get_git_log_for_file("nonexistent.py")
    assert result == ""


# ── _get_git_blame_summary ──────────────────────────────────────────────────────


def test_blame_summary_parses_porcelain(monkeypatch):
    porcelain = "\n".join([
        "abcdef1234567890abcdef1234567890abcdef12 1 1 3",
        "author Alice",
        "author-mail <alice@example.com>",
        "author-time 1700000000",
        "author-tz +0000",
        "committer Alice",
        "committer-mail <alice@example.com>",
        "committer-time 1700000000",
        "committer-tz +0000",
        "summary feat: initial commit",
        "filename src/auth.py",
        "\tdef login():",
    ])

    call_count = 0

    def fake_run(cmd, **kwargs):
        nonlocal call_count
        call_count += 1
        if "blame" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout=porcelain, stderr="")
        raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = _get_git_blame_summary("src/auth.py")
    assert "Alice" in result
    assert "1 commit(s)" in result
    assert "feat: initial commit" in result


def test_blame_summary_with_function_uses_git_log_l(monkeypatch):
    log_output = "abc123 Alice: feat: add login function\n+def login():\n+    pass"

    def fake_run(cmd, **kwargs):
        if "-L" in str(cmd):
            return subprocess.CompletedProcess(cmd, 0, stdout=log_output, stderr="")
        raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = _get_git_blame_summary("src/auth.py", function="login")
    assert "Alice" in result
    assert "login" in result


def test_blame_summary_returns_empty_on_error(monkeypatch):
    def fake_run(cmd, **kwargs):
        raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = _get_git_blame_summary("nonexistent.py")
    assert result == ""


# ── WHY_SYSTEM_PROMPT ───────────────────────────────────────────────────────────


def test_system_prompt_is_distinct_from_search():
    from devmemory.core.llm_client import SYSTEM_PROMPT as SEARCH_PROMPT
    assert WHY_SYSTEM_PROMPT != SEARCH_PROMPT
    assert "code historian" in WHY_SYSTEM_PROMPT
    assert "why" in WHY_SYSTEM_PROMPT.lower()


# ── _synthesize_why ─────────────────────────────────────────────────────────────


def test_synthesize_why_raises_without_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    monkeypatch.setattr(
        "devmemory.core.llm_client._get_llm_config",
        lambda: ("", "gpt-4o-mini", "openai"),
    )

    from devmemory.core.llm_client import LLMError

    try:
        why._synthesize_why("file.py", "", [], "some git context")
    except LLMError as e:
        assert "no_api_key" in str(e)
    else:
        assert False, "Expected LLMError"


def test_synthesize_why_builds_correct_user_message(monkeypatch):
    captured = {}

    def fake_call_llm(system_prompt, user_msg, **kwargs):
        captured["system_prompt"] = system_prompt
        captured["user_msg"] = user_msg
        return "The answer"

    monkeypatch.setattr("devmemory.core.llm_client.call_llm", fake_call_llm)

    memories = [
        {"text": "Added auth module", "type": "semantic", "score": 0.3, "topics": ["auth"]},
    ]

    result = why._synthesize_why("src/auth.py", "login", memories, "git log here")

    assert result == "The answer"
    assert captured["system_prompt"] == WHY_SYSTEM_PROMPT
    assert "src/auth.py" in captured["user_msg"]
    assert "login" in captured["user_msg"]
    assert "git log here" in captured["user_msg"]
    assert "Added auth module" in captured["user_msg"]


# ── run_why integration (mocked) ────────────────────────────────────────────────


def _make_fake_memory(id: str, text: str, score: float, memory_type: str = "semantic"):
    from devmemory.core.ams_client import MemoryResult
    return MemoryResult(
        id=id,
        text=text,
        score=score,
        topics=["test"],
        entities=[],
        memory_type=memory_type,
        created_at="2026-01-01",
    )


def test_run_why_raw_shows_git_history_when_search_fails(monkeypatch, capsys):
    """When AMS search fails, raw mode should still show git history."""
    monkeypatch.setattr(
        "devmemory.commands.why.DevMemoryConfig.load",
        lambda: type("C", (), {"ams_endpoint": "http://localhost:8000", "namespace": ""})(),
    )

    class FakeClient:
        def __init__(self, **kw):
            pass

        def health_check(self):
            pass

        def search_memories(self, **kw):
            raise Exception("AMS down")

    monkeypatch.setattr(why, "AMSClient", FakeClient)

    # Mock git cat-file to pass file check
    original_run = subprocess.run

    def fake_run(cmd, **kwargs):
        cmd_str = " ".join(str(c) for c in cmd)
        if "cat-file" in cmd_str:
            return subprocess.CompletedProcess(cmd, 0)
        if "git log" in cmd_str:
            return subprocess.CompletedProcess(
                cmd, 0,
                stdout="abc123|Dev|feat: add file|2026-01-01T00:00:00+00:00",
                stderr="",
            )
        if "blame" in cmd_str:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        return original_run(cmd, **kwargs)

    monkeypatch.setattr(subprocess, "run", fake_run)

    # Should not raise — just print git history
    why.run_why(filepath="src/auth.py", raw=True)


def test_run_why_exits_for_missing_file(monkeypatch):
    monkeypatch.setattr(
        "devmemory.commands.why.DevMemoryConfig.load",
        lambda: type("C", (), {"ams_endpoint": "http://localhost:8000", "namespace": ""})(),
    )

    class FakeClient:
        def __init__(self, **kw):
            pass

        def health_check(self):
            pass

    monkeypatch.setattr(why, "AMSClient", FakeClient)

    def fake_run(cmd, **kwargs):
        raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(ClickExit):
        why.run_why(filepath="nonexistent/file.py", raw=True)


def test_run_why_exits_when_ams_unreachable(monkeypatch):
    monkeypatch.setattr(
        "devmemory.commands.why.DevMemoryConfig.load",
        lambda: type("C", (), {"ams_endpoint": "http://localhost:8000", "namespace": ""})(),
    )

    class FakeClient:
        def __init__(self, **kw):
            pass

        def health_check(self):
            raise ConnectionError("Connection refused")

    monkeypatch.setattr(why, "AMSClient", FakeClient)

    with pytest.raises(ClickExit):
        why.run_why(filepath="src/auth.py")
