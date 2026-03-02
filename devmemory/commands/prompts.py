from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table
from rich.syntax import Syntax

from devmemory.core.config import DevMemoryConfig
from devmemory.attribution.cloud_storage import CloudStorage

console = Console()

prompts_app = typer.Typer(name="prompts", help="Browse prompt memories")


@prompts_app.callback(invoke_without_command=True)
def default_prompts(
    ctx: typer.Context,
    limit: int = typer.Option(50, "--limit", "-l", help="Max prompt memories to list."),
    namespace: str = typer.Option(None, "--namespace", "-n", help="Filter by namespace."),
):
    """List prompt memories stored (newest first)."""
    if ctx.invoked_subcommand:
        return
    run_prompts(limit=limit, namespace=namespace)


def run_prompts(
    limit: int = 50,
    namespace: str = "",
    all_repos: bool = False,
) -> None:
    config = DevMemoryConfig.load()
    if all_repos:
        ns = namespace or None
    else:
        ns = namespace or config.get_active_namespace()

    if not config.api_key:
        console.print("[yellow]API key required. Run: devmemory config set api_key YOUR_KEY[/yellow]")
        raise typer.Exit(1)

    with CloudStorage(api_key=config.api_key) as client:
        result = client.search(
            query="prompt",
            limit=min(limit, 200),
            namespace=ns,
        )

        if result.get("error"):
            console.print(f"[red]Search failed: {result.get('message')}[/red]")
            raise typer.Exit(1)

        memories = result.get("data", {}).get("results", [])

        if not memories:
            console.print("[yellow]No prompt memories found.[/yellow]")
            raise typer.Exit(0)

        table = Table(title=f"Prompt memories (namespace={ns or 'default'})")
        table.add_column("id", style="cyan", width=14)
        table.add_column("text (excerpt)", style="white", max_width=70, overflow="fold")

        for r in memories[:limit]:
            text = r.get("text", "")[:70]
            table.add_row(r.get("id", "")[:14], text)

        console.print(table)
        console.print(f"\n[dim]Showing {min(len(memories), limit)} of {len(memories)} results[/dim]")


def run_search_prompts(
    query: str,
    limit: int = 20,
    namespace: str = "",
) -> None:
    """Search prompt memories by query."""
    config = DevMemoryConfig.load()
    ns = namespace or config.get_active_namespace()

    if not config.api_key:
        console.print("[yellow]API key required. Run: devmemory config set api_key YOUR_KEY[/yellow]")
        raise typer.Exit(1)

    with CloudStorage(api_key=config.api_key) as client:
        result = client.search(
            query=query,
            limit=limit,
            namespace=ns,
        )

        if result.get("error"):
            console.print(f"[red]Search failed: {result.get('message')}[/red]")
            raise typer.Exit(1)

        memories = result.get("data", {}).get("results", [])

        if not memories:
            console.print(f"[yellow]No results for '{query}'.[/yellow]")
            raise typer.Exit(0)

        for r in memories:
            console.print(f"\n[cyan]{r.get('id', 'unknown')[:12]}[/cyan]")
            console.print(r.get("text", "")[:500])


@prompts_app.command("search")
def search_prompts(
    query: str = typer.Argument(..., help="Search query"),
    limit: int = typer.Option(20, "--limit", "-l", help="Max results"),
    namespace: str = typer.Option(None, "--namespace", "-n", help="Filter by namespace"),
):
    """Search prompt memories by query."""
    run_search_prompts(query=query, limit=limit, namespace=namespace)
