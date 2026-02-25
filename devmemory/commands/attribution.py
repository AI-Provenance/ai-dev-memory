import typer
from rich.console import Console
from rich.table import Table
from rich.syntax import Syntax

from devmemory.attribution.config import AttributionConfig
from devmemory.attribution.redis_storage import AttributionStorage
from devmemory.core.config import DevMemoryConfig
from devmemory.core.logging_config import get_logger

log = get_logger(__name__)
console = Console()

attribution_app = typer.Typer(name="attribution", help="Manage AI attribution data in Redis")


def _get_namespace() -> str:
    """Get the active namespace from config or use default."""
    try:
        config = DevMemoryConfig.load()
        return config.get_active_namespace()
    except Exception:
        return "default"


@attribution_app.command("list")
def list_attributions(
    namespace: str = typer.Option(
        None, "--namespace", "-n", help="Filter by namespace (auto-detected if not provided)"
    ),
    limit: int = typer.Option(20, "--limit", "-l", help="Number of keys to show"),
):
    """List stored attributions in Redis."""
    ns = namespace or _get_namespace()

    try:
        config = AttributionConfig.load()
        storage = AttributionStorage(config.redis_url)
    except Exception as e:
        console.print(f"[red]Failed to connect to Redis: {e}[/red]")
        raise typer.Exit(1)

    try:
        pattern = f"attr:{ns}:*:*"
        keys = storage.redis.keys(pattern)

        if not keys:
            console.print(f"[yellow]No attributions found for namespace '{ns}'[/yellow]")
            console.print(f"[dim]Hint: try --namespace default or run devmemory sync first[/dim]")
            raise typer.Exit(0)

        table = Table(title=f"Attributions in '{ns}' ({len(keys)} total)")
        table.add_column("File", style="cyan")
        table.add_column("Commit", style="yellow")
        table.add_column("Ranges", style="green")
        table.add_column("Author", style="magenta")

        for key in keys[:limit]:
            # Key format: attr:{namespace}:{filepath}:{commit_sha}
            # namespace includes repo_id, so we need to find filepath and commit_sha
            # by looking from the end
            parts = key.split(":")

            # Last part is commit_sha
            commit_sha = parts[-1]
            # Second to last is filepath
            filepath = parts[-2]
            # Everything else is namespace parts
            namespace_from_key = ":".join(parts[1:-2])

            ranges = storage.redis.hgetall(key)
            range_count = len([k for k in ranges.keys() if k != "_meta"])

            ai_count = sum(1 for v in ranges.values() if "ai" in v)
            author = "AI" if ai_count > 0 else "Human"

            table.add_row(filepath, commit_sha[:8], str(range_count), author)

        console.print(table)
        console.print(f"\n[dim]Showing {min(limit, len(keys))} of {len(keys)} keys[/dim]")

    finally:
        storage.close()


@attribution_app.command("show")
def show_attribution(
    filepath: str = typer.Argument(..., help="File path to show"),
    commit_sha: str = typer.Argument(None, help="Commit SHA (latest if not provided)"),
    namespace: str = typer.Option(None, "--namespace", "-n", help="Namespace"),
):
    """Show detailed attribution for a specific file."""
    ns = namespace or _get_namespace()

    try:
        config = AttributionConfig.load()
        storage = AttributionStorage(config.redis_url)
    except Exception as e:
        console.print(f"[red]Failed to connect to Redis: {e}[/red]")
        raise typer.Exit(1)

    try:
        if not commit_sha:
            pattern = f"attr:{ns}:{filepath}:*"
            keys = storage.redis.keys(pattern)
            if not keys:
                console.print(f"[red]No attribution found for {filepath}[/red]")
                raise typer.Exit(1)
            keys = sorted(keys)
            commit_sha = keys[-1].split(":")[-1]
            key = f"attr:{ns}:{filepath}:{commit_sha}"
        else:
            key = f"attr:{ns}:{filepath}:{commit_sha}"

        data = storage.redis.hgetall(key)

        if not data:
            console.print(f"[red]No attribution found for {filepath}@{commit_sha[:8]}[/red]")
            raise typer.Exit(1)

        console.print(f"\n[bold]File:[/bold] {filepath}")
        console.print(f"[bold]Namespace:[/bold] {ns}")
        console.print(f"[bold]Commit:[/bold] {commit_sha[:8]}")
        console.print()

        table = Table(title="Line Attribution")
        table.add_column("Lines", style="cyan")
        table.add_column("Author", style="yellow")
        table.add_column("Tool", style="green")
        table.add_column("Model", style="magenta")
        table.add_column("Prompt ID", style="dim")

        import json

        for range_str, attr_json in sorted(data.items()):
            if range_str == "_meta":
                continue
            try:
                attr = json.loads(attr_json)
                table.add_row(
                    range_str,
                    attr.get("author", "unknown"),
                    attr.get("tool", "-"),
                    attr.get("model", "-"),
                    (attr.get("prompt_id", "-")[:12] + "...") if attr.get("prompt_id") else "-",
                )
            except json.JSONDecodeError:
                table.add_row(range_str, "[red]parse error[/red]", "-", "-", "-")

        console.print(table)

    finally:
        storage.close()


@attribution_app.command("deployments")
def list_deployments(
    namespace: str = typer.Option(None, "--namespace", "-n", help="Filter by namespace"),
    limit: int = typer.Option(20, "--limit", "-l", help="Number to show"),
):
    """List stored deployment mappings."""
    ns = namespace or _get_namespace()

    try:
        config = AttributionConfig.load()
        storage = AttributionStorage(config.redis_url)
    except Exception as e:
        console.print(f"[red]Failed to connect to Redis: {e}[/red]")
        raise typer.Exit(1)

    try:
        pattern = f"deploy:{ns}:*"
        keys = storage.redis.keys(pattern)

        if not keys:
            console.print(f"[yellow]No deployments found for namespace '{ns}'[/yellow]")
            raise typer.Exit(0)

        table = Table(title=f"Deployments in '{ns}' ({len(keys)} total)")
        table.add_column("Release", style="cyan")
        table.add_column("Commit SHA", style="yellow")

        for key in keys[:limit]:
            parts = key.split(":")
            if len(parts) >= 3:
                release = parts[2]
                commit_sha = storage.redis.get(key) or "N/A"
                table.add_row(release, commit_sha[:8])

        console.print(table)

    finally:
        storage.close()


@attribution_app.command("lookup")
def lookup_line(
    filepath: str = typer.Argument(..., help="File path"),
    lineno: int = typer.Argument(..., help="Line number"),
    commit_sha: str = typer.Argument(None, help="Commit SHA (auto-detected if not provided)"),
    namespace: str = typer.Option(None, "--namespace", "-n", help="Namespace"),
):
    """Look up AI attribution for a specific line."""
    ns = namespace or _get_namespace()

    try:
        config = AttributionConfig.load()
        storage = AttributionStorage(config.redis_url)
    except Exception as e:
        console.print(f"[red]Failed to connect to Redis: {e}[/red]")
        raise typer.Exit(1)

    try:
        if not commit_sha:
            pattern = f"attr:{ns}:{filepath}:*"
            keys = storage.redis.keys(pattern)
            if not keys:
                console.print(f"[red]No attribution found for {filepath}[/red]")
                raise typer.Exit(1)
            keys = sorted(keys)
            commit_sha = keys[-1].split(":")[-1]

        result = storage.get_attribution(ns, filepath, commit_sha, lineno)

        console.print(f"\n[bold]File:[/bold] {filepath}")
        console.print(f"[bold]Line:[/bold] {lineno}")
        console.print(f"[bold]Namespace:[/bold] {ns}")
        console.print(f"[bold]Commit:[/bold] {commit_sha[:8]}")
        console.print()

        if result.get("author") == "ai":
            console.print(f"[green]✓ AI-generated[/green]")
        else:
            console.print(f"[yellow]Human-written[/yellow]")

        if result.get("tool"):
            console.print(f"[bold]Tool:[/bold] {result['tool']}")
        if result.get("model"):
            console.print(f"[bold]Model:[/bold] {result['model']}")
        if result.get("prompt_id"):
            console.print(f"[bold]Prompt ID:[/bold] {result['prompt_id']}")
        if result.get("author_email"):
            console.print(f"[bold]Author:[/bold] {result['author_email']}")
        console.print(f"[bold]Confidence:[/bold] {result.get('confidence', 0.95)}")

    finally:
        storage.close()


if __name__ == "__main__":
    attribution_app()
