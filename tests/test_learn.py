from pathlib import Path

from devmemory.commands import learn


def test_parse_frontmatter_and_sections(tmp_path):
    content = "\n".join(
        [
            "---",
            "topics: [architecture, decisions]",
            "entities: [Redis, AMS]",
            "---",
            "",
            "## Why Redis",
            "",
            "Text about Redis.",
            "",
            "## CLI Pattern",
            "",
            "Text about CLI.",
        ]
    )
    path = tmp_path / "architecture.md"
    path.write_text(content)
    memories = learn._parse_knowledge_file(path, tmp_path)
    assert len(memories) == 2
    ids = {m["id"] for m in memories}
    assert len(ids) == 2
    topics_sets = {tuple(m["topics"]) for m in memories}
    assert ("architecture", "decisions") in topics_sets or ("decisions", "architecture") in topics_sets
    for m in memories:
        assert m["session_id"].startswith("knowledge:")

