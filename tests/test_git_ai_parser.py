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

