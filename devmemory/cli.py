import typer
from typing import Optional
from devmemory import __version__
from devmemory.core.config import DevMemoryConfig
from devmemory.commands.config_cmd import app as config_app
from devmemory.commands.add import run_add
from devmemory.commands.attribution import attribution_app
from devmemory.commands.context import run_context
from devmemory.commands.install import run_install
from devmemory.commands.learn import run_learn
from devmemory.commands.prompts import prompts_app
from devmemory.commands.search import run_search
from devmemory.commands.status import run_status
from devmemory.commands.stats import run_stats
from devmemory.commands.sync import run_sync
from devmemory.commands.why import run_why
from devmemory.commands.summarize import run_summarize, run_generate_architecture_summary

app = typer.Typer(
    name="devmemory",
    help="DevMemory - AI coding attribution tracking.",
    no_args_is_help=True,
)


def _get_mode():
    """Get the current installation mode."""
    try:
        config = DevMemoryConfig.load()
        return config.installation_mode or "local"
    except Exception:
        return "local"


@app.command()
def version(
    short: bool = typer.Option(False, "--short", help="Show just the version number"),
):
    """Show the devmemory version."""
    from rich.console import Console

    console = Console()
    if short:
        console.print(__version__)
    else:
        console.print(f"[bold]devmemory[/bold] version [cyan]{__version__}[/cyan]")


app.add_typer(config_app, name="config", help="Manage devmemory configuration.")
app.add_typer(attribution_app, name="attribution", help="Manage AI code line attributions.")
app.add_typer(prompts_app, name="prompts", help="Browse and search Git AI prompts.")


@app.command()
def sync(
    latest: bool = typer.Option(False, "--latest", help="Sync only the latest commit."),
    all_commits: bool = typer.Option(False, "--all", help="Sync all commits (ignore last synced state)."),
    ai_only: bool = typer.Option(True, "--ai-only/--include-human", help="Only sync commits with AI notes."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be synced without sending."),
    limit: int = typer.Option(50, "--limit", help="Max commits to process."),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Minimal output (single summary line)."),
    batch_size: int = typer.Option(50, "--batch-size", help="Number of memories per sync request."),
    local_enrichment: bool = typer.Option(
        True, "--local-enrichment", help="Perform AI enrichment locally (vs cloud API)."
    ),
    all_branches: bool = typer.Option(False, "--all-branches", help="Sync commits from all local branches."),
):
    """Sync Git AI notes to attribution storage."""
    run_sync(
        latest=latest,
        all_commits=all_commits,
        ai_only=ai_only,
        dry_run=dry_run,
        limit=limit,
        quiet=quiet,
        batch_size=batch_size,
        local_enrichment=local_enrichment,
        all_branches=all_branches,
    )


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query (natural language)."),
    limit: int = typer.Option(10, "--limit", "-n", help="Max results to return."),
    namespace: str = typer.Option("", "--namespace", "-ns", help="Filter by namespace."),
    topic: list[str] = typer.Option([], "--topic", "-t", help="Filter by topic(s)."),
    memory_type: str = typer.Option("", "--type", help="Filter by memory type (episodic, semantic)."),
    threshold: float = typer.Option(
        0.75,
        "--threshold",
        help="Relevance threshold (0-1, lower=stricter). Results with distance above this are filtered.",
    ),
    raw: bool = typer.Option(
        False, "--raw", help="Raw output mode: skip answer synthesis and show memory panels directly."
    ),
    recency_boost: float = typer.Option(
        0.0, "--recency", help="Apply recency boost (0.0=none, 1.0=full priority on recent)."
    ),
):
    """Search the project knowledgebase via Cloud API."""
    run_search(
        query=query,
        limit=limit,
        namespace=namespace,
        topic=topic or None,
        memory_type=memory_type,
        threshold=threshold,
        raw=raw,
        recency_boost=recency_boost,
    )


@app.command()
def stats(
    days: int = typer.Option(30, "--days", "-d", help="Time window in days (default: 30)."),
    output: str = typer.Option("table", "--output", "-o", help="Output format: table, json, csv."),
    by_topic: bool = typer.Option(False, "--by-topic", help="Group stats by topic."),
    by_entity: bool = typer.Option(False, "--by-entity", help="Group stats by entity."),
    since_commit: str = typer.Option("", "--since", help="Show stats since a specific commit SHA."),
    create_view: bool = typer.Option(False, "--create-view", help="Create a persistent summary view from these stats."),
    view_name: str = typer.Option("", "--view-name", help="Name for the summary view (if --create-view)."),
    list_views: bool = typer.Option(False, "--list-views", help="List all stats summary views."),
    delete_view: str = typer.Option("", "--delete-view", help="Delete a specific summary view by name."),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Minimal output, suitable for scripting."),
):
    """Show project statistics via Cloud API."""
    run_stats(
        days=days,
        output=output,
        by_topic=by_topic,
        by_entity=by_entity,
        since_commit=since_commit,
        create_view=create_view,
        view_name=view_name,
        list_views=list_views,
        delete_view=delete_view,
        quiet=quiet,
    )


@app.command()
def add(
    text: str = typer.Argument("", help="The memory text to store."),
    memory_type: str = typer.Option("semantic", "--type", "-t", help="Memory type (episodic, semantic)."),
    topic: list[str] = typer.Option([], "--topic", help="Topic tags (can specify multiple)."),
    entity: list[str] = typer.Option([], "--entity", "-e", help="Entity tags (can specify multiple)."),
    interactive: bool = typer.Option(False, "--interactive", "-i", help="Interactive mode with prompts."),
):
    """Add a memory directly (design decisions, gotchas, conventions, etc.)."""
    run_add(text=text, memory_type=memory_type, topics=topic or None, entities=entity or None, interactive=interactive)


@app.command()
def learn(
    path: str = typer.Argument("", help="Path to knowledge directory (default: .devmemory/knowledge/)."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be synced without sending."),
):
    """Sync knowledge files (markdown) into the memory store."""
    run_learn(path=path, dry_run=dry_run)


@app.command()
def context(
    output: str = typer.Option("", "--output", "-o", help="Output file path (default: .devmemory/CONTEXT.md)."),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="No terminal output, just write the file."),
):
    """Generate a context briefing from memory based on current git state."""
    run_context(output=output, quiet=quiet)


@app.command()
def why(
    filepath: str = typer.Argument(..., help="File path relative to repo root (e.g. src/auth.py)."),
    function: str = typer.Argument("", help="Optional function or class name to focus on."),
    limit: int = typer.Option(15, "--limit", "-n", help="Max memories to use for synthesis."),
    raw: bool = typer.Option(False, "--raw", help="Show raw memories and git history without LLM synthesis."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show verbose explanation and sources."),
):
    """Explain why a file (or function) exists and how it evolved."""
    run_why(filepath=filepath, function=function, limit=limit, raw=raw, verbose=verbose)


@app.command()
def summarize(
    view_type: str = typer.Option("project", "--type", "-t", help="Type of summary: project or architecture."),
    time_window: Optional[int] = typer.Option(None, "--time-window", "-w", help="Time window in days for summary."),
    manual: bool = typer.Option(False, "--manual", "-m", help="Generate manual summary instead of creating view."),
    list_views: bool = typer.Option(False, "--list", "-l", help="List all summary views."),
    delete_view: Optional[str] = typer.Option(None, "--delete", "-d", help="Delete a specific summary view by ID."),
):
    """Create and manage project-level summaries."""
    run_summarize(
        view_type=view_type, time_window=time_window, manual=manual, list_views=list_views, delete_view=delete_view
    )


@app.command()
def architecture(
    output: str = typer.Option(".devmemory/architecture-summary.md", "--output", "-o", help="Output file path."),
    time_window: int = typer.Option(30, "--time-window", "-w", help="Time window in days for analysis."),
):
    """Generate comprehensive architecture summary document."""
    run_generate_architecture_summary(output=output, time_window=time_window)


@app.command()
def install(
    skip_hook: bool = typer.Option(False, "--skip-hook", help="Skip post-commit hook installation."),
    interactive: bool = typer.Option(
        False, "--interactive", "-i", help="Interactive mode to select installation mode (local/cloud)."
    ),
    force_mode: str = typer.Option("", "--mode", help="Force installation mode: 'local' or 'cloud'."),
    api_key: str = typer.Option("", "--api-key", help="API key for cloud mode (get one at aiprove.org)."),
):
    """Set up Git hooks and local storage."""
    run_install(
        skip_hook=skip_hook,
        interactive=interactive,
        force_mode=force_mode,
        api_key=api_key,
    )


@app.command()
def status():
    """Show system status."""
    run_status()


def main():
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
