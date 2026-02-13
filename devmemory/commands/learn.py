from __future__ import annotations

import hashlib
import re
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from devmemory.core.config import DevMemoryConfig
from devmemory.core.ams_client import AMSClient

console = Console()

DEFAULT_KNOWLEDGE_DIR = ".devmemory/knowledge"


def _parse_frontmatter(content: str) -> tuple[dict, str]:
    if not content.startswith("---"):
        return {}, content

    end = content.find("---", 3)
    if end == -1:
        return {}, content

    frontmatter_raw = content[3:end].strip()
    body = content[end + 3:].strip()

    meta: dict = {}
    for line in frontmatter_raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()

        list_match = re.match(r"^\[(.+)]$", value)
        if list_match:
            items = [v.strip().strip("'\"") for v in list_match.group(1).split(",")]
            meta[key] = [i for i in items if i]
        else:
            meta[key] = value.strip("'\"")

    return meta, body


def _split_sections(body: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []

    lines = body.splitlines()
    current_heading = ""
    current_lines: list[str] = []

    for line in lines:
        heading_match = re.match(r"^(#{1,2})\s+(.+)$", line)
        if heading_match:
            if current_lines:
                text = "\n".join(current_lines).strip()
                if text:
                    sections.append((current_heading, text))
            current_heading = heading_match.group(2).strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        text = "\n".join(current_lines).strip()
        if text:
            sections.append((current_heading, text))

    return sections


def _memory_id(filepath: str, section_heading: str) -> str:
    raw = f"knowledge:{filepath}:{section_heading}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def _parse_knowledge_file(filepath: Path, base_dir: Path) -> list[dict]:
    content = filepath.read_text()
    meta, body = _parse_frontmatter(content)

    default_topics = meta.get("topics", [])
    if isinstance(default_topics, str):
        default_topics = [default_topics]
    default_entities = meta.get("entities", [])
    if isinstance(default_entities, str):
        default_entities = [default_entities]
    default_type = meta.get("type", "semantic")

    rel_path = str(filepath.relative_to(base_dir))

    sections = _split_sections(body)

    if not sections:
        stripped = body.strip()
        if stripped:
            sections = [(filepath.stem.replace("-", " ").replace("_", " ").title(), stripped)]

    memories = []
    for heading, text in sections:
        if not text.strip():
            continue

        memory_text = f"{heading}\n\n{text}" if heading else text

        section_topics = list(default_topics)
        if not section_topics:
            section_topics = [filepath.stem.replace("-", " ").replace("_", " ")]

        memories.append({
            "id": _memory_id(rel_path, heading or filepath.stem),
            "text": memory_text,
            "memory_type": default_type,
            "topics": section_topics,
            "entities": list(default_entities),
            "session_id": f"knowledge:{rel_path}",
        })

    return memories


def run_learn(
    path: str = "",
    dry_run: bool = False,
):
    config = DevMemoryConfig.load()

    knowledge_dir = Path(path) if path else Path.cwd() / DEFAULT_KNOWLEDGE_DIR

    if not knowledge_dir.exists():
        if not path:
            console.print(f"[yellow]No knowledge directory found at {DEFAULT_KNOWLEDGE_DIR}[/yellow]")
            console.print()
            console.print("[dim]Create it with some markdown files:[/dim]")
            console.print(f"  [cyan]mkdir -p {DEFAULT_KNOWLEDGE_DIR}[/cyan]")
            console.print()
            console.print("[dim]Example knowledge file (.devmemory/knowledge/architecture.md):[/dim]")
            console.print("""  [dim]---[/dim]
  [dim]topics: [architecture, decisions][/dim]
  [dim]---[/dim]

  [dim]## Why We Chose Redis[/dim]
  [dim]We chose Redis with vector search over dedicated vector DBs[/dim]
  [dim]because it's already part of our stack and reduces complexity.[/dim]

  [dim]## CLI Design Pattern[/dim]
  [dim]All commands live in devmemory/commands/ with a run_<name>()[/dim]
  [dim]entry point. CLI flags are defined in cli.py.[/dim]""")
            raise typer.Exit(0)
        else:
            console.print(f"[red]Directory not found: {knowledge_dir}[/red]")
            raise typer.Exit(1)

    md_files = sorted(knowledge_dir.glob("**/*.md"))
    if not md_files:
        console.print(f"[yellow]No markdown files found in {knowledge_dir}[/yellow]")
        raise typer.Exit(0)

    all_memories: list[dict] = []
    file_counts: list[tuple[str, int]] = []

    for md_file in md_files:
        memories = _parse_knowledge_file(md_file, knowledge_dir)
        rel = str(md_file.relative_to(knowledge_dir))
        file_counts.append((rel, len(memories)))
        for m in memories:
            m["namespace"] = config.namespace or "default"
            if config.user_id:
                m["user_id"] = config.user_id
        all_memories.extend(memories)

    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 1))
    table.add_column("File", style="cyan")
    table.add_column("Memories", justify="right")
    for filename, count in file_counts:
        table.add_row(filename, str(count))

    console.print(f"\n[bold]Knowledge files in {knowledge_dir}[/bold]\n")
    console.print(table)
    console.print(f"\n[bold]Total: {len(all_memories)} memories from {len(md_files)} file(s)[/bold]")

    if dry_run:
        console.print("\n[dim]Dry run — showing parsed memories:[/dim]\n")
        for m in all_memories:
            title = m["text"].splitlines()[0][:60] if m["text"] else "(empty)"
            topics_str = ", ".join(m.get("topics", []))
            console.print(f"  [{m['memory_type']}] {title}")
            if topics_str:
                console.print(f"    [dim]topics: {topics_str}[/dim]")
        console.print(f"\n[yellow]Dry run complete. Remove --dry-run to sync.[/yellow]")
        return

    if not all_memories:
        console.print("[yellow]No memories to sync.[/yellow]")
        return

    client = AMSClient(base_url=config.ams_endpoint)

    try:
        client.health_check()
    except Exception as e:
        console.print(f"[red]Cannot reach AMS at {config.ams_endpoint}: {e}[/red]")
        raise typer.Exit(1)

    try:
        client.create_memories(all_memories, deduplicate=True)
    except Exception as e:
        console.print(f"[red]Failed to sync knowledge: {e}[/red]")
        raise typer.Exit(1)

    console.print(f"\n[bold green]Synced {len(all_memories)} memories from knowledge files.[/bold green]")
