from devmemory.core import git_ai_parser


def test_parse_ai_note_skips_json_and_markers():
    raw = "\n".join(
        [
            "devmemory/core/memory_formatter.py",
            "  aaa111 1-5",
            "---",
            "{",
            '  "schema_version": "authorship/3.0.0",',
            "}",
        ]
    )
    files = git_ai_parser.parse_ai_note(raw)
    assert len(files) == 1
    f = files[0]
    assert f.filepath == "devmemory/core/memory_formatter.py"
    assert "aaa111" in f.prompt_lines
    assert len(f.prompt_lines["aaa111"]) == 1


def test_get_per_file_diffs_splits_by_diff_header(monkeypatch):
    diff = "\n".join(
        [
            "diff --git a/file1.py b/file1.py",
            "index 0000000..1111111 100644",
            "--- a/file1.py",
            "+++ b/file1.py",
            "+line1",
            "+line2",
            "diff --git a/dir/file2.py b/dir/file2.py",
            "index 0000000..2222222 100644",
            "--- a/dir/file2.py",
            "+++ b/dir/file2.py",
            "+other1",
        ]
    )

    def fake_full_diff(sha):
        return diff

    monkeypatch.setattr(git_ai_parser, "get_commit_diff_full", fake_full_diff)
    result = git_ai_parser.get_per_file_diffs("dummy")
    assert "file1.py" in result
    assert "dir/file2.py" in result
    assert "line1" in result["file1.py"]
    assert "other1" in result["dir/file2.py"]


def test_parse_ai_note_metadata_extracts_prompts_from_note():
    raw = """src/main.rs
 abcd1234abcd1234 1-10,15-20
---
{"schema_version": "authorship/3.0.0", "base_commit_sha": "abc", "prompts": {
  "abcd1234abcd1234": {
    "agent_id": {"tool": "cursor", "id": "u1", "model": "claude-4.5"},
    "human_author": "Dev",
    "messages": [
      {"type": "user", "text": "Add error handling"},
      {"type": "assistant", "text": "I'll add it..."}
    ],
    "total_additions": 25, "total_deletions": 5, "accepted_lines": 20, "overriden_lines": 0
  }
}}"""
    meta = git_ai_parser._parse_ai_note_metadata(raw)
    assert meta is not None
    assert meta.get("schema_version") == "authorship/3.0.0"
    prompts = git_ai_parser._prompts_from_note_metadata(raw)
    assert "abcd1234abcd1234" in prompts
    rec = prompts["abcd1234abcd1234"]
    msgs = git_ai_parser._messages_from_note_prompt_record(rec)
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user" and msgs[0]["content"] == "Add error handling"
    assert msgs[1]["role"] == "assistant" and "add it" in msgs[1]["content"]


def test_note_prompt_record_for_id_matches_prefix():
    note_prompts = {"4097f8f1253aa7b0": {"messages": [{"type": "user", "text": "fix CLI"}]}}
    assert git_ai_parser._note_prompt_record_for_id(note_prompts, "4097f8f1253aa7b0") is not None
    assert git_ai_parser._note_prompt_record_for_id(note_prompts, "4097f8f1") is not None

