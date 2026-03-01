"""Search command - Cloud API version."""

import typer
from rich.console import Console
from rich.panel import Panel

from devmemory.core.config import DevMemoryConfig
from devmemory.attribution.cloud_storage import CloudStorage

console = Console()


def run_search(
    query: str,
    limit: int = 10,
    namespace: str = "",
    topic: list[str] | None = None,
    memory_type: str = "",
    threshold: float = 0.75,
    raw: bool = False,
    recency_boost: float = 0.0,
    all_repos: bool = False,
):
    """Search via Cloud API (aiprove.org)."""
    config = DevMemoryConfig.load()

    # Check if API key is configured
    if not config.api_key:
        console.print("[yellow]⚠ This feature requires Cloud Edition[/yellow]")
        console.print("[dim]Get an API key at: https://aiprove.org[/dim]")
        console.print("")
        console.print("Local mode features available now:")
        console.print("  - devmemory attribution lookup <file>")
        console.print("  - devmemory sync")
        console.print("  - devmemory status")
        raise typer.Exit(0)

    # Use Cloud API (aiprove.org)
    client = CloudStorage(api_key=config.api_key)

    try:
        health = client.health_check()
        if health.get("status") != "ok":
            console.print(f"[red]Cloud API unhealthy: {health.get('message', 'Unknown error')}[/red]")
            raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Cannot reach Cloud API: {e}[/red]")
        console.print("[dim]Check your API key or try again later.[/dim]")
        raise typer.Exit(1)

    # Use cloud search
    try:
        ns = namespace or config.get_active_namespace()
        response = client.search(query=query, limit=limit, namespace=ns)

        if response.get("error"):
            console.print(f"[red]Search failed: {response['error']}[/red]")
            raise typer.Exit(1)

        results = response.get("results", [])
        message = response.get("message", "")

        if message and not results:
            console.print(f"[yellow]{message}[/yellow]")
            console.print(f"[dim]Quota remaining: {response.get('quota_remaining', 'N/A')}[/dim]")
            raise typer.Exit(0)

        # Display results
        if not results:
            console.print("[yellow]No results found.[/yellow]")
            raise typer.Exit(0)

        console.print(f"[green]Found {len(results)} results[/green]")
        console.print("")

        # Display simplified results
        for i, result in enumerate(results[:limit], 1):
            text = result.get("text", "No text")
            console.print(
                Panel(text[:200] + "..." if len(text) > 200 else text, title=f"Result {i}", border_style="dim")
            )

        console.print("")
        console.print(f"[dim]Quota remaining: {response.get('quota_remaining', 'N/A')}[/dim]")

    except Exception as e:
        console.print(f"[red]Search failed: {e}[/red]")
        raise typer.Exit(1)
