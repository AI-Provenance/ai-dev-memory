import typer
from rich.console import Console
from rich.table import Table
from rich.syntax import Syntax

from devmemory.attribution.config import AttributionConfig
from devmemory.attribution.sqlite_storage import SQLiteAttributionStorage
from devmemory.core.config import DevMemoryConfig
from devmemory.core.logging_config import get_logger

log = get_logger(__name__)
console = Console()

attribution_app = typer.Typer(name="attribution", help="Manage AI attribution (local SQLite storage)")


def _get_storage():
    """Get the attribution storage (SQLite for local mode)."""
    config = DevMemoryConfig.load()

    # Local mode: Use SQLite
    sqlite_path = config.get_sqlite_path()
    return SQLiteAttributionStorage(sqlite_path), "sqlite"


def _get_namespace() -> str:
    """Get the active namespace from config or use default."""
    try:
        config = DevMemoryConfig.load()
        return config.get_active_namespace()
    except Exception:
        return "default"


def _show_mode():
    """Show the current mode in CLI output."""
    config = DevMemoryConfig.load()
    mode = config.installation_mode or "cloud"
    console.print(f"[dim]Mode: {mode}[/dim]")


@attribution_app.command("list")
def list_attributions(
    namespace: str = typer.Option(
        None, "--namespace", "-n", help="Filter by namespace (auto-detected if not provided)"
    ),
    limit: int = typer.Option(20, "--limit", "-l", help="Number of keys to show"),
):
    """List stored attributions."""
    ns = namespace or _get_namespace()

    try:
        storage, storage_type = _get_storage()
    except Exception as e:
        console.print(f"[red]Failed to connect to storage: {e}[/red]")
        raise typer.Exit(1)

    try:
        # SQLite listing
        conn = storage._get_conn()
        cursor = conn.execute(
            "SELECT DISTINCT filepath, commit_sha FROM attributions WHERE namespace = ? LIMIT ?", (ns, limit)
        )
        rows = cursor.fetchall()

        if not rows:
            console.print(f"[yellow]No attributions found for namespace '{ns}'[/yellow]")
            console.print(f"[dim]Hint: run devmemory sync first[/dim]")
            raise typer.Exit(0)

        table = Table(title=f"Attributions in '{ns}' ({len(rows)} files)")
        table.add_column("File", style="cyan")
        table.add_column("Commit", style="yellow")
        table.add_column("Author", style="magenta")

        for row in rows:
            filepath, commit_sha = row
            # Get author info
            cursor = conn.execute(
                "SELECT author FROM attributions WHERE namespace = ? AND filepath = ? AND commit_sha = ? LIMIT 1",
                (ns, filepath, commit_sha),
            )
            author_row = cursor.fetchone()
            author = author_row[0] if author_row else "unknown"

            table.add_row(filepath, commit_sha[:8], author)

        console.print(table)
        console.print(f"\n[dim]Showing {len(rows)} files[/dim]")

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
        storage, storage_type = _get_storage()
    except Exception as e:
        console.print(f"[red]Failed to connect to storage: {e}[/red]")
        raise typer.Exit(1)

    try:
        if storage_type == "redis":
            # Redis implementation
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
        else:
            # SQLite implementation
            conn = storage._get_conn()

            if not commit_sha:
                cursor = conn.execute(
                    "SELECT commit_sha FROM file_latest WHERE namespace = ? AND filepath = ?", (ns, filepath)
                )
                row = cursor.fetchone()
                if not row:
                    console.print(f"[red]No attribution found for {filepath}[/red]")
                    raise typer.Exit(1)
                commit_sha = row[0]

            cursor = conn.execute(
                "SELECT line_start, line_end, author, tool, model, prompt_id FROM attributions WHERE namespace = ? AND filepath = ? AND commit_sha = ?",
                (ns, filepath, commit_sha),
            )
            rows = cursor.fetchall()

            if not rows:
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

            for row in rows:
                line_start, line_end, author, tool, model, prompt_id = row
                lines = f"{line_start}-{line_end}" if line_start != line_end else str(line_start)
                prompt_display = (prompt_id[:12] + "...") if prompt_id else "-"
                table.add_row(
                    lines,
                    author or "unknown",
                    tool or "-",
                    model or "-",
                    prompt_display,
                )

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
    """Look up AI attribution for a specific line (uses latest commit by default)."""
    ns = namespace or _get_namespace()

    try:
        storage, storage_type = _get_storage()
    except Exception as e:
        console.print(f"[red]Failed to connect to storage: {e}[/red]")
        raise typer.Exit(1)

    try:
        if commit_sha:
            # Explicit commit provided - use it
            result = storage.get_attribution(ns, filepath, commit_sha, lineno)
        else:
            # Use latest attribution (recommended)
            result = storage.get_latest_attribution(ns, filepath, lineno)
            if not result:
                console.print(f"[red]No attribution found for {filepath}:{lineno}[/red]")
                raise typer.Exit(1)
            commit_sha = result.get("commit_sha", "unknown")

        console.print(f"\n[bold]File:[/bold] {filepath}")
        console.print(f"[bold]Line:[/bold] {lineno}")
        console.print(f"[bold]Namespace:[/bold] {ns}")
        console.print(f"[bold]Commit:[/bold] {commit_sha[:8] if commit_sha != 'unknown' else 'unknown'}")
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


@attribution_app.command("history")
def file_history(
    filepath: str = typer.Argument(..., help="File path"),
    limit: int = typer.Option(20, "--limit", "-l", help="Number of commits to show"),
    namespace: str = typer.Option(None, "--namespace", "-n", help="Namespace"),
):
    """Show all commits that have attribution data for a file."""
    ns = namespace or _get_namespace()

    try:
        storage, storage_type = _get_storage()
    except Exception as e:
        console.print(f"[red]Failed to connect to storage: {e}[/red]")
        raise typer.Exit(1)

    if storage_type != "redis":
        console.print(f"[yellow]History command is only supported in cloud (Redis) mode.[/yellow]")
        raise typer.Exit(1)

    try:
        # Get all attribution keys for this file
        pattern = f"attr:{ns}:{filepath}:*"
        all_keys = storage.redis.keys(pattern)

        if not all_keys:
            console.print(f"[yellow]No attribution data found for {filepath}[/yellow]")
            raise typer.Exit(0)

        # Extract commit SHAs and get range counts
        commits = []
        import json

        for key in all_keys:
            commit_sha = key.split(":")[-1]
            ranges = storage.redis.hgetall(key)
            range_count = len([k for k in ranges.keys() if k != "_meta"])

            # Try to get timestamp from history, otherwise use "unknown"
            history_key = storage._history_key(ns, filepath)
            timestamp = storage.redis.zscore(history_key, commit_sha)

            commits.append(
                {
                    "commit_sha": commit_sha,
                    "timestamp": int(timestamp) if timestamp else None,
                    "ranges": range_count,
                }
            )

        # Sort by timestamp (newest first), None timestamps go to end
        commits.sort(key=lambda x: x["timestamp"] if x["timestamp"] else 0, reverse=True)
        commits = commits[:limit]

        console.print(f"\n[bold]File:[/bold] {filepath}")
        console.print(f"[bold]Namespace:[/bold] {ns}")
        console.print()

        table = Table(title=f"Attribution History ({len(commits)} commits)")
        table.add_column("Commit", style="yellow")
        table.add_column("Date", style="cyan")
        table.add_column("AI Blocks", style="green")

        from datetime import datetime

        for entry in commits:
            commit_sha = entry["commit_sha"]
            timestamp = entry["timestamp"]
            range_count = entry["ranges"]

            # Format date
            if timestamp:
                dt = datetime.fromtimestamp(timestamp)
                date_str = dt.strftime("%Y-%m-%d %H:%M")
            else:
                date_str = "unknown"

            table.add_row(commit_sha[:8], date_str, str(range_count))

        console.print(table)

    finally:
        storage.close()


if __name__ == "__main__":
    attribution_app()
