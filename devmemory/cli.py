import typer
from typing import Optional
from devmemory.commands.config_cmd import app as config_app
from devmemory.commands.add import run_add
from devmemory.commands.context import run_context
from devmemory.commands.install import run_install
from devmemory.commands.learn import run_learn
from devmemory.commands.prompts import run_prompts
from devmemory.commands.search import run_search
from devmemory.commands.status import run_status
from devmemory.commands.stats import run_stats
from devmemory.commands.sync import run_sync
from devmemory.commands.why import run_why
from devmemory.commands.summarize import run_summarize, run_generate_architecture_summary

app = typer.Typer(
    name="devmemory",
    help="Sync AI coding context from Git AI to Redis Agent Memory Server for semantic search and recall.",
    no_args_is_help=True,
)

app.add_typer(config_app, name="config", help="Manage devmemory configuration.")


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
        True, "--local-enrichment/--ams-enrichment", help="Whether to perform enrichment locally or rely on AMS."
    ),
    all_branches: bool = typer.Option(False, "--all-branches", help="Sync commits from all local branches."),
):
    """Sync Git AI notes to Redis AMS."""
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
    """Search the project knowledgebase with AI-powered answer synthesis."""
    run_search(
        query=query,
        limit=limit,
        namespace=namespace,
        topic=topic,
        memory_type=memory_type,
        threshold=threshold,
        raw=raw,
        recency_boost=recency_boost,
    )


@app.command()
def prompts(
    limit: int = typer.Option(50, "--limit", "-n", help="Max prompt memories to list."),
    namespace: str = typer.Option("", "--namespace", "-ns", help="Filter by namespace."),
):
    """List prompt memories stored in AMS (newest first). Use to verify what prompts are in Redis."""
    run_prompts(limit=limit, namespace=namespace)


@app.command()
def status():
    """Show system status."""
    run_status()


@app.command()
def stats(
    team: bool = typer.Option(False, "--team", "-t", help="Show team-wide stats instead of individual."),
    days: Optional[int] = typer.Option(None, "--days", "-d", help="Filter to last N days (e.g., 30, 90)."),
    all_time: bool = typer.Option(False, "--all-time", help="Show all-time stats (no time filter)."),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Minimal output."),
    create_views: bool = typer.Option(False, "--create-views", help="Create AMS summary views for team stats."),
):
    """Show code contribution stats (AI vs Human).

    By default shows individual stats. Use --team for team-wide stats.
    """
    run_stats(team=team, days=days, all_time=all_time, quiet=quiet, create_views=create_views)


@app.command()
def add(
    text: str = typer.Argument("", help="Memory text to store. If empty, launches interactive mode."),
    memory_type: str = typer.Option(
        "semantic", "--type", help="Memory type: semantic (facts/decisions) or episodic (events)."
    ),
    topic: list[str] = typer.Option([], "--topic", "-t", help="Topic tags (can specify multiple)."),
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
    manual: bool = typer.Option(False, "--manual", "-m", help="Generate manual summary instead of creating AMS view."),
    list_views: bool = typer.Option(False, "--list", "-l", help="List all summary views."),
    delete_view: Optional[str] = typer.Option(None, "--delete", "-d", help="Delete a specific summary view by ID."),
):
    """Create and manage project-level summaries using Redis AMS summary views."""
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
    skip_cursor: bool = typer.Option(False, "--skip-cursor", help="Skip Cursor MCP config."),
    skip_antigravity: bool = typer.Option(False, "--skip-antigravity", help="Skip Antigravity MCP config."),
    skip_opencode: bool = typer.Option(False, "--skip-opencode", help="Skip OpenCode MCP config."),
    skip_rule: bool = typer.Option(False, "--skip-rule", help="Skip Cursor agent rule installation."),
    mcp_endpoint: str = typer.Option("", "--mcp-endpoint", help="Override MCP server endpoint."),
):
    """Set up Git hooks, MCP configs, and agent coordination rules."""
    run_install(
        skip_hook=skip_hook,
        skip_cursor=skip_cursor,
        skip_antigravity=skip_antigravity,
        skip_opencode=skip_opencode,
        skip_rule=skip_rule,
        mcp_endpoint=mcp_endpoint,
    )


def main():
    app()


if __name__ == "__main__":
    main()
