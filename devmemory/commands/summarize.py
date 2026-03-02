"""Summarize command for DevMemory.

This module provides project and architecture summary capabilities.
All business logic is handled by the Cloud API.
"""

from __future__ import annotations

import typer
import os
from typing import Optional

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from devmemory.core.config import DevMemoryConfig
from devmemory.attribution.cloud_storage import CloudStorage

console = Console()


def run_summarize(
    view_type: str = "project",
    time_window: Optional[int] = None,
    manual: bool = False,
    list_views: bool = False,
    delete_view: Optional[str] = None,
):
    """Create and manage project-level summaries using Cloud API."""

    config = DevMemoryConfig.load()
    namespace = config.get_active_namespace()

    with CloudStorage(api_key=config.api_key) as client:
        if list_views:
            _list_summary_views(client)
            return

        if delete_view:
            _delete_summary_view(client, delete_view)
            return

        # Generate summary via API
        result = client.summarize(
            view_type=view_type,
            namespace=namespace,
            time_window=time_window,
            manual=manual,
        )

        if result.get("error"):
            console.print(f"[red]Error: {result.get('message', 'Unknown error')}[/red]")
            raise typer.Exit(1)

        if manual:
            # Display manual summary
            summary = result.get("data", {}).get("summary", "")
            console.print(
                Panel(
                    summary,
                    title="[bold green]Project Summary[/bold green]",
                    border_style="green",
                    padding=(1, 2),
                )
            )
        else:
            # Display created view info
            view = result.get("data", {}).get("view", {})
            view_name = view.get("name", "Unknown")
            console.print(f"[green]Created {view_type} summary view: {view_name}[/green]")

        console.print("[dim]Use `devmemory summarize --list` to see all views[/dim]")


def _list_summary_views(client: CloudStorage):
    """List all registered summary views"""
    result = client.list_summary_views()

    if result.get("error"):
        console.print(f"[red]Error: {result.get('message', 'Unknown error')}[/red]")
        raise typer.Exit(1)

    views = result.get("data", {}).get("views", [])

    if not views:
        console.print("[yellow]No summary views found.[/yellow]")
        return

    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 1))
    table.add_column("ID", style="dim")
    table.add_column("Name", style="cyan")
    table.add_column("Source")
    table.add_column("Group By")
    table.add_column("Continuous")

    for view in views:
        table.add_row(
            view.get("id", ""),
            view.get("name", "(unnamed)"),
            view.get("source", ""),
            ", ".join(view.get("group_by", [])) if view.get("group_by") else "-",
            "✓" if view.get("continuous") else "✗",
        )

    console.print("[bold]Summary Views[/bold]")
    console.print(table)


def _delete_summary_view(client: CloudStorage, view_id: str):
    """Delete a summary view"""
    result = client.delete_summary_view(view_id)

    if result.get("error"):
        console.print(f"[red]Error: {result.get('message', 'Unknown error')}[/red]")
        raise typer.Exit(1)

    console.print(f"[green]Deleted summary view {view_id}[/green]")


def run_generate_architecture_summary(
    output: str = ".devmemory/architecture-summary.md",
    time_window: Optional[int] = 30,
):
    """Generate a comprehensive architecture summary document"""

    config = DevMemoryConfig.load()
    namespace = config.get_active_namespace()

    console.print("[dim]Generating architecture summary...[/dim]")

    with CloudStorage(api_key=config.api_key) as client:
        result = client.generate_architecture_summary(
            output=output,
            namespace=namespace,
            time_window=time_window or 30,
        )

        if result.get("error"):
            console.print(f"[red]Error: {result.get('message', 'Unknown error')}[/red]")
            raise typer.Exit(1)

        output_path = result.get("data", {}).get("output", output)
        console.print(f"[green]Architecture summary written to {output_path}[/green]")
