import typer
from devmemory.commands.config_cmd import app as config_app

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
):
    """Sync Git AI notes to Redis AMS."""
    from devmemory.commands.sync import run_sync
    run_sync(latest=latest, all_commits=all_commits, ai_only=ai_only, dry_run=dry_run, limit=limit, quiet=quiet)


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query (natural language)."),
    limit: int = typer.Option(10, "--limit", "-n", help="Max results to return."),
    namespace: str = typer.Option("", "--namespace", "-ns", help="Filter by namespace."),
    topic: list[str] = typer.Option([], "--topic", "-t", help="Filter by topic(s)."),
    memory_type: str = typer.Option("", "--type", help="Filter by memory type (episodic, semantic)."),
    threshold: float = typer.Option(0.75, "--threshold", help="Relevance threshold (0-1, lower=stricter). Results with distance above this are filtered."),
    raw: bool = typer.Option(False, "--raw", help="Raw output mode: skip answer synthesis and show memory panels directly."),
):
    """Search the project knowledgebase with AI-powered answer synthesis."""
    from devmemory.commands.search import run_search
    run_search(query=query, limit=limit, namespace=namespace, topic=topic, memory_type=memory_type, threshold=threshold, raw=raw)


@app.command()
def status():
    """Show system status."""
    from devmemory.commands.status import run_status
    run_status()


@app.command()
def add(
    text: str = typer.Argument("", help="Memory text to store. If empty, launches interactive mode."),
    memory_type: str = typer.Option("semantic", "--type", help="Memory type: semantic (facts/decisions) or episodic (events)."),
    topic: list[str] = typer.Option([], "--topic", "-t", help="Topic tags (can specify multiple)."),
    entity: list[str] = typer.Option([], "--entity", "-e", help="Entity tags (can specify multiple)."),
    interactive: bool = typer.Option(False, "--interactive", "-i", help="Interactive mode with prompts."),
):
    """Add a memory directly (design decisions, gotchas, conventions, etc.)."""
    from devmemory.commands.add import run_add
    run_add(text=text, memory_type=memory_type, topics=topic or None, entities=entity or None, interactive=interactive)


@app.command()
def learn(
    path: str = typer.Argument("", help="Path to knowledge directory (default: .devmemory/knowledge/)."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be synced without sending."),
):
    """Sync knowledge files (markdown) into the memory store."""
    from devmemory.commands.learn import run_learn
    run_learn(path=path, dry_run=dry_run)


@app.command()
def context(
    output: str = typer.Option("", "--output", "-o", help="Output file path (default: .devmemory/CONTEXT.md)."),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="No terminal output, just write the file."),
):
    """Generate a context briefing from memory based on current git state."""
    from devmemory.commands.context import run_context
    run_context(output=output, quiet=quiet)


@app.command()
def install(
    skip_hook: bool = typer.Option(False, "--skip-hook", help="Skip post-commit hook installation."),
    skip_mcp: bool = typer.Option(False, "--skip-mcp", help="Skip Cursor MCP config."),
    skip_rule: bool = typer.Option(False, "--skip-rule", help="Skip Cursor agent rule installation."),
    mcp_endpoint: str = typer.Option("", "--mcp-endpoint", help="Override MCP server endpoint."),
):
    """Set up Git hooks, Cursor MCP config, and agent coordination rules."""
    from devmemory.commands.install import run_install
    run_install(skip_hook=skip_hook, skip_mcp=skip_mcp, skip_rule=skip_rule, mcp_endpoint=mcp_endpoint)


def main():
    app()


if __name__ == "__main__":
    main()
