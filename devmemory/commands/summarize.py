from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from typing import Optional
from datetime import datetime, timedelta

from devmemory.core.config import DevMemoryConfig
from devmemory.core.ams_client import AMSClient, SummaryView
from devmemory.core.memory_formatter import generate_commit_summary
from devmemory.core.git_ai_parser import get_commits_since

console = Console()

PROJECT_SUMMARY_PROMPT = """\
You are an AI architect analyzing a software project's evolution. 
Given the project's commit history, generate a comprehensive summary that includes:

1. **Architecture Overview**: High-level system design and components
2. **Key Decisions**: Major architectural choices and their rationale
3. **Evolution Timeline**: How the architecture has changed over time
4. **Current State**: What the system looks like now
5. **Technical Debt**: Known issues and areas for improvement
6. **Patterns**: Recurring design patterns and conventions

Focus on the "why" behind changes, not just "what" changed. 
Highlight tradeoffs, lessons learned, and emerging patterns.
"""

ARCHITECTURE_SUMMARY_PROMPT = """\
You are analyzing architectural decisions in a codebase. 
Given commit messages, code changes, and context, identify and summarize:

1. **Component Boundaries**: How the system is modularized
2. **Data Flow**: How information moves through the system
3. **Integration Points**: APIs, interfaces, and contracts
4. **Scalability Approaches**: How the system handles growth
5. **Failure Modes**: Common error patterns and recovery strategies

Provide concrete examples from the actual code changes.
"""


def _create_project_summary_view(
    client: AMSClient,
    namespace: str,
    time_window_days: Optional[int] = None,
    custom_prompt: Optional[str] = None
) -> SummaryView:
    """Create a summary view for project-level architecture analysis"""
    
    view_config = {
        "name": f"Project Architecture Summary - {namespace}",
        "source": "long_term",
        "group_by": ["namespace"],
        "filters": {
            "namespace": {"eq": namespace},
            "memory_type": {"eq": "semantic"}
        },
        "prompt": custom_prompt or PROJECT_SUMMARY_PROMPT,
        "model_name": "gpt-4o",  # Use a powerful model for summarization
    }
    
    if time_window_days:
        view_config["time_window_days"] = time_window_days
    
    return client.create_summary_view(view_config)


def _create_architecture_evolution_view(
    client: AMSClient,
    namespace: str,
    time_window_days: Optional[int] = None
) -> SummaryView:
    """Create a summary view for architecture evolution tracking"""
    
    view_config = {
        "name": f"Architecture Evolution - {namespace}",
        "source": "long_term",
        "group_by": ["namespace"],
        "filters": {
            "namespace": {"eq": namespace},
            "topics": {"any": ["architecture", "decisions", "refactoring"]}
        },
        "prompt": ARCHITECTURE_SUMMARY_PROMPT,
        "model_name": "gpt-4o",
    }
    
    if time_window_days:
        view_config["time_window_days"] = time_window_days
    
    return client.create_summary_view(view_config)


def _generate_manual_project_summary(
    namespace: str,
    time_window_days: Optional[int] = None
) -> str:
    """Generate a project summary by analyzing recent commits"""
    
    # Get recent commits
    since_date = None
    if time_window_days:
        since_date = (datetime.now() - timedelta(days=time_window_days)).strftime("%Y-%m-%d")
    
    commits = get_commits_since(since=since_date) if since_date else get_commits_since()
    
    if not commits:
        return "No commits found in the specified time range."
    
    # Generate summaries for key commits
    summaries = []
    for commit in commits[:10]:  # Limit to 10 most recent commits
        summary = generate_commit_summary(commit, namespace=namespace)
        if summary:
            summaries.append(f"## {commit.subject}\n\n{summary['text']}\n")
    
    if not summaries:
        return "No summarizable commits found."
    
    return "# Project Summary\n\n" + "\n".join(summaries)


def run_summarize(
    view_type: str = "project",
    time_window: Optional[int] = None,
    manual: bool = False,
    list_views: bool = False,
    delete_view: Optional[str] = None,
):
    """Create and manage project-level summaries using Redis AMS summary views."""
    
    config = DevMemoryConfig.load()
    client = AMSClient(base_url=config.ams_endpoint)
    
    try:
        client.health_check()
    except Exception as e:
        console.print(f"[red]Cannot reach AMS at {config.ams_endpoint}: {e}[/red]")
        raise typer.Exit(1)
    
    namespace = config.get_active_namespace()
    
    if list_views:
        _list_summary_views(client)
        return
    
    if delete_view:
        _delete_summary_view(client, delete_view)
        return
    
    if manual:
        summary = _generate_manual_project_summary(namespace, time_window)
        console.print(Panel(
            summary,
            title="[bold green]Project Summary[/bold green]",
            border_style="green",
            padding=(1, 2),
        ))
        return
    
    # Create appropriate summary view
    if view_type == "project":
        view = _create_project_summary_view(client, namespace, time_window)
        console.print(f"[green]Created project summary view: {view.name} (ID: {view.id})[/green]")
    elif view_type == "architecture":
        view = _create_architecture_evolution_view(client, namespace, time_window)
        console.print(f"[green]Created architecture evolution view: {view.name} (ID: {view.id})[/green]")
    else:
        console.print(f"[red]Unknown view type: {view_type}[/red]")
        raise typer.Exit(1)
    
    console.print("[dim]Use `devmemory summarize --list` to see all views[/dim]")
    console.print("[dim]Results will be available via Redis AMS summary view system[/dim]")


def _list_summary_views(client: AMSClient):
    """List all registered summary views"""
    try:
        views = client.list_summary_views()
        
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
                view.id,
                view.name or "(unnamed)",
                view.source,
                ", ".join(view.group_by) if view.group_by else "-",
                "✓" if view.continuous else "✗"
            )
        
        console.print("[bold]Summary Views[/bold]")
        console.print(table)
        
    except Exception as e:
        console.print(f"[red]Failed to list summary views: {e}[/red]")
        raise typer.Exit(1)


def _delete_summary_view(client: AMSClient, view_id: str):
    """Delete a summary view"""
    try:
        client.delete_summary_view(view_id)
        console.print(f"[green]Deleted summary view {view_id}[/green]")
    except Exception as e:
        console.print(f"[red]Failed to delete summary view: {e}[/red]")
        raise typer.Exit(1)


def run_generate_architecture_summary(
    output: str = "architecture-summary.md",
    time_window: Optional[int] = 30,
):
    """Generate a comprehensive architecture summary document"""
    
    config = DevMemoryConfig.load()
    namespace = config.get_active_namespace()
    
    console.print("[dim]Generating architecture summary...[/dim]")
    
    # Generate manual summary first
    manual_summary = _generate_manual_project_summary(namespace, time_window)
    
    # Create architecture evolution view
    config = DevMemoryConfig.load()
    client = AMSClient(base_url=config.ams_endpoint)
    
    try:
        view = _create_architecture_evolution_view(client, namespace, time_window)
        console.print(f"[dim]Created architecture view: {view.id}[/dim]")
    except Exception as e:
        console.print(f"[yellow]Could not create architecture view: {e}[/yellow]")
    
    # Write comprehensive summary
    with open(output, "w") as f:
        f.write(f"# Architecture Summary\n\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
        f.write(f"Namespace: {namespace}\n\n")
        f.write(f"---\n\n")
        f.write(manual_summary)
        f.write(f"\n---\n\n")
        f.write(f"## Architecture Evolution\n\n")
        f.write(f"For detailed architecture evolution analysis, check Redis AMS summary view: {view.id}\n")
    
    console.print(f"[green]Architecture summary written to {output}[/green]")
