from devmemory.core import memory_formatter
from devmemory.core.git_ai_parser import CommitNote, FileAttribution, PromptData, CommitStats


def test_format_commit_as_memories_produces_layers(monkeypatch):
    diff = "\n".join(
        [
            "diff --git a/devmemory/core/ams_client.py b/devmemory/core/ams_client.py",
            "index 0000000..1111111 100644",
            "--- a/devmemory/core/ams_client.py",
            "+++ b/devmemory/core/ams_client.py",
            "+from httpx import Client",
            "+class AMSClient:",
            "+    pass",
        ]
    )

    def fake_per_file_diffs(sha):
        return {"devmemory/core/ams_client.py": diff}

    def fake_commit_diff(sha):
        return "devmemory/core/ams_client.py | 3 ++"

    monkeypatch.setattr(memory_formatter, "get_per_file_diffs", fake_per_file_diffs)
    monkeypatch.setattr(memory_formatter, "get_commit_diff", fake_commit_diff)

    prompt = PromptData(
        prompt_id="aaa111",
        tool="cursor",
        model="claude-4.6-opus-high-thinking",
        human_author="Test User",
        messages=[{"role": "user", "content": "Add AMS client"}],
        total_additions=3,
        total_deletions=0,
        accepted_lines=3,
        overridden_lines=0,
    )
    stats = CommitStats(
        human_additions=0,
        ai_additions=3,
        ai_accepted=3,
        mixed_additions=0,
        total_ai_additions=3,
        total_ai_deletions=0,
        time_waiting_for_ai=5.0,
        git_diff_added_lines=3,
        git_diff_deleted_lines=0,
        tool_model_breakdown={},
    )
    note = CommitNote(
        sha="abc123def456",
        author_name="Test User",
        author_email="test@example.com",
        subject="feat: add AMS client",
        date="2026-02-10T12:00:00+00:00",
        files=[FileAttribution(filepath="devmemory/core/ams_client.py", prompt_lines={"aaa111": ["1-3"]})],
        has_ai_note=True,
        raw_note="",
        prompts={"aaa111": prompt},
        stats=stats,
        body="Adds an HTTP client for Redis AMS.",
    )

    memories = memory_formatter.format_commit_as_memories(note, namespace="ns", user_id="user")
    assert len(memories) >= 2
    types = {m["memory_type"] for m in memories}
    assert "semantic" in types
    assert "episodic" in types
    summary = memories[0]["text"]
    assert "feat: add AMS client" in summary
    assert "AI contribution" in summary
    per_file = [m for m in memories if m["memory_type"] == "episodic"][0]
    assert "devmemory/core/ams_client.py" in per_file["text"]
    assert "class AMSClient" in per_file["text"]

