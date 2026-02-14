from pathlib import Path

import pytest

from devmemory.commands.status import get_cursor_rules_status

VALID_MAIN = """---
description: DevMemory agent coordination
alwaysApply: true
---

# DevMemory
You have access to the `agent-memory` MCP server.
Use search_long_term_memory() for lookups.
"""

VALID_CONTEXT = """---
description: Auto-generated project context from DevMemory
alwaysApply: true
---

# DevMemory Auto-Context
If `.devmemory/CONTEXT.md` exists, read it at the start of every task.
Run `devmemory context` in the terminal to refresh it.
"""


def _rules_dir(tmp_path: Path) -> Path:
    d = tmp_path / ".cursor" / "rules"
    d.mkdir(parents=True)
    return d


def test_cursor_rules_installed_when_both_valid(tmp_path):
    rules = _rules_dir(tmp_path)
    (rules / "devmemory.mdc").write_text(VALID_MAIN)
    (rules / "devmemory-context.mdc").write_text(VALID_CONTEXT)
    status = get_cursor_rules_status(tmp_path)
    assert "[green]installed[/green]" in status
    assert "devmemory.mdc" in status and "devmemory-context.mdc" in status


def test_cursor_rules_not_installed_when_no_rules(tmp_path):
    status = get_cursor_rules_status(tmp_path)
    assert "[yellow]not installed[/yellow]" in status
    assert "run: devmemory install" in status


def test_cursor_rules_partially_installed_missing_context_rule(tmp_path):
    rules = _rules_dir(tmp_path)
    (rules / "devmemory.mdc").write_text(VALID_MAIN)
    status = get_cursor_rules_status(tmp_path)
    assert "[yellow]partially installed[/yellow]" in status
    assert "missing context rule" in status


def test_cursor_rules_partially_installed_missing_main_rule(tmp_path):
    rules = _rules_dir(tmp_path)
    (rules / "devmemory-context.mdc").write_text(VALID_CONTEXT)
    status = get_cursor_rules_status(tmp_path)
    assert "[yellow]partially installed[/yellow]" in status
    assert "missing main rule" in status


def test_cursor_rules_context_rule_outdated_missing_always_apply(tmp_path):
    rules = _rules_dir(tmp_path)
    (rules / "devmemory.mdc").write_text(VALID_MAIN)
    context_bad = VALID_CONTEXT.replace("alwaysApply: true", "alwaysApply: false")
    (rules / "devmemory-context.mdc").write_text(context_bad)
    status = get_cursor_rules_status(tmp_path)
    assert "context rule outdated or missing alwaysApply" in status


def test_cursor_rules_context_rule_outdated_missing_marker(tmp_path):
    rules = _rules_dir(tmp_path)
    (rules / "devmemory.mdc").write_text(VALID_MAIN)
    context_bad = "---\nalwaysApply: true\n---\n\nGeneric rule with no expected marker strings."
    (rules / "devmemory-context.mdc").write_text(context_bad)
    status = get_cursor_rules_status(tmp_path)
    assert "context rule outdated or missing alwaysApply" in status


def test_cursor_rules_main_rule_outdated_missing_always_apply(tmp_path):
    rules = _rules_dir(tmp_path)
    main_bad = VALID_MAIN.replace("alwaysApply: true", "alwaysApply: false")
    (rules / "devmemory.mdc").write_text(main_bad)
    (rules / "devmemory-context.mdc").write_text(VALID_CONTEXT)
    status = get_cursor_rules_status(tmp_path)
    assert "main rule outdated or missing alwaysApply" in status


def test_cursor_rules_main_rule_outdated_missing_mcp_refs(tmp_path):
    rules = _rules_dir(tmp_path)
    main_bad = """---
alwaysApply: true
---
Generic rule with no MCP references.
"""
    (rules / "devmemory.mdc").write_text(main_bad)
    (rules / "devmemory-context.mdc").write_text(VALID_CONTEXT)
    status = get_cursor_rules_status(tmp_path)
    assert "main rule outdated or missing alwaysApply" in status


