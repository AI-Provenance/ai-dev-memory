import hashlib

import typer
from rich.console import Console
from rich.panel import Panel

from devmemory.core.config import DevMemoryConfig
from devmemory.core.ams_client import AMSClient

console = Console()

VALID_TYPES = ("semantic", "episodic")


def _generate_id(text: str) -> str:
    return hashlib.sha256(f"manual:{text}".encode()).hexdigest()[:24]


def run_add(
    text: str = "",
    memory_type: str = "semantic",
    topics: list[str] | None = None,
    entities: list[str] | None = None,
    interactive: bool = False,
):
    config = DevMemoryConfig.load()
    client = AMSClient(base_url=config.ams_endpoint, auth_token=config.get_auth_token())

    try:
        client.health_check()
    except Exception as e:
        console.print(f"[red]Cannot reach AMS at {config.ams_endpoint}: {e}[/red]")
        raise typer.Exit(1)

    if interactive or not text:
        text = _interactive_prompt(memory_type, topics, entities)
        if text is None:
            raise typer.Exit(0)
        return

    if memory_type not in VALID_TYPES:
        console.print(f"[red]Invalid memory type '{memory_type}'. Must be one of: {', '.join(VALID_TYPES)}[/red]")
        raise typer.Exit(1)

    memory = {
        "id": _generate_id(text),
        "text": text,
        "memory_type": memory_type,
        "namespace": config.get_active_namespace(),
    }
    if topics:
        memory["topics"] = topics
    if entities:
        memory["entities"] = entities
    if config.user_id:
        memory["user_id"] = config.user_id

    try:
        client.create_memories([memory])
    except Exception as e:
        console.print(f"[red]Failed to store memory: {e}[/red]")
        raise typer.Exit(1)

    console.print(
        Panel(
            text,
            title=f"[bold green]Stored[/bold green] [{memory_type}]",
            border_style="green",
            padding=(0, 1),
        )
    )
    if topics:
        console.print(f"  [dim]Topics: {', '.join(topics)}[/dim]")
    if entities:
        console.print(f"  [dim]Entities: {', '.join(entities)}[/dim]")


def _interactive_prompt(
    default_type: str = "semantic",
    default_topics: list[str] | None = None,
    default_entities: list[str] | None = None,
) -> str | None:
    config = DevMemoryConfig.load()
    client = AMSClient(base_url=config.ams_endpoint, auth_token=config.get_auth_token())

    console.print("[bold]Add a memory[/bold]\n")
    console.print("[dim]Types of knowledge to store:[/dim]")
    console.print("  - Architecture decisions and rationale")
    console.print("  - Known gotchas and workarounds")
    console.print("  - Project conventions and patterns")
    console.print("  - Bug root causes")
    console.print("  - API quirks and limitations")
    console.print()

    text = typer.prompt("Memory text (what do you want to remember?)")
    if not text.strip():
        console.print("[yellow]No text provided, aborting.[/yellow]")
        return None

    type_input = typer.prompt(
        "Memory type",
        default=default_type,
        show_default=True,
    )
    if type_input not in VALID_TYPES:
        console.print(f"[yellow]Invalid type, using 'semantic'[/yellow]")
        type_input = "semantic"

    topics_default = ", ".join(default_topics) if default_topics else ""
    topics_input = typer.prompt(
        "Topics (comma-separated, e.g. architecture,patterns)",
        default=topics_default,
        show_default=bool(topics_default),
    )
    topics = [t.strip() for t in topics_input.split(",") if t.strip()] if topics_input else []

    entities_default = ", ".join(default_entities) if default_entities else ""
    entities_input = typer.prompt(
        "Entities (comma-separated, e.g. Redis,httpx)",
        default=entities_default,
        show_default=bool(entities_default),
    )
    entities = [e.strip() for e in entities_input.split(",") if e.strip()] if entities_input else []

    memory = {
        "id": _generate_id(text),
        "text": text,
        "memory_type": type_input,
        "namespace": config.get_active_namespace(),
    }
    if topics:
        memory["topics"] = topics
    if entities:
        memory["entities"] = entities
    if config.user_id:
        memory["user_id"] = config.user_id

    console.print()
    console.print(
        Panel(
            text,
            title=f"[bold]Preview[/bold] [{type_input}]",
            border_style="dim",
            padding=(0, 1),
        )
    )
    if topics:
        console.print(f"  [dim]Topics: {', '.join(topics)}[/dim]")
    if entities:
        console.print(f"  [dim]Entities: {', '.join(entities)}[/dim]")
    console.print()

    if not typer.confirm("Store this memory?", default=True):
        console.print("[yellow]Cancelled.[/yellow]")
        return None

    try:
        client.create_memories([memory])
    except Exception as e:
        console.print(f"[red]Failed to store memory: {e}[/red]")
        raise typer.Exit(1)

    console.print("[bold green]Memory stored.[/bold green]")
    return text
