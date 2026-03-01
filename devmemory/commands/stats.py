"""Stats command - Cloud API version."""

from typing import Optional
import typer
from rich.console import Console
from rich.table import Table

from devmemory.core.config import DevMemoryConfig
from devmemory.core.utils import get_repo_root
from devmemory.attribution.cloud_storage import CloudStorage

console = Console()


def run_stats(
    days: int = 30,
    output: str = "table",
    by_topic: bool = False,
    by_entity: bool = False,
    since_commit: str = "",
    create_view: bool = False,
    view_name: str = "",
    list_views: bool = False,
    delete_view: str = "",
    quiet: bool = False,
):
    """Show project statistics via Cloud API (aiprove.org)."""
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

    # Use cloud stats
    try:
        response = client.get_stats(days=days)

        if response.get("error"):
            console.print(f"[red]Stats request failed: {response['error']}[/red]")
            raise typer.Exit(1)

        ai_pct = response.get("ai_percentage", 0)
        human_pct = response.get("human_percentage", 0)
        total = response.get("total_commits", 0)
        ai_commits = response.get("ai_commits", 0)
        human_commits = response.get("human_commits", 0)

        # Display stats
        if not quiet:
            console.print(f"\n[bold]Code Statistics[/bold] [dim](Last {days} days)[/dim]\n")

            table = Table(show_header=True, header_style="bold")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", justify="right")

            table.add_row("AI Commits", f"{ai_commits}")
            table.add_row("Human Commits", f"{human_commits}")
            table.add_row("Total Commits", f"{total}")
            table.add_row("", "")
            table.add_row("AI Percentage", f"{ai_pct}%", style="yellow" if ai_pct > 50 else "green")
            table.add_row("Human Percentage", f"{human_pct}%", style="green" if human_pct > 50 else "yellow")

            console.print(table)
            console.print("")
            console.print(f"[dim]Quota remaining: {response.get('quota_remaining', 'N/A')}[/dim]")
        else:
            # Quiet mode - just numbers
            console.print(f"{ai_pct},{human_pct},{total},{ai_commits},{human_commits}")

    except Exception as e:
        console.print(f"[red]Stats request failed: {e}[/red]")
        raise typer.Exit(1)
