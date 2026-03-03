import subprocess
import typer
from rich.console import Console
from rich.table import Table
from rich.syntax import Syntax

from devmemory.attribution.sqlite_storage import SQLiteAttributionStorage
from devmemory.core.config import DevMemoryConfig
from devmemory.core.logging_config import get_logger
from devmemory.core.git_ai_parser import _git_ai_prefix

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


def _get_blame_commit(filepath: str, lineno: int) -> str | None:
    """Get the commit SHA that last modified a specific line using git-ai blame.

    Uses git-ai blame instead of regular git blame because it integrates with
    the AI attribution system and provides better information about AI-generated code.
    """
    try:
        cmd = _git_ai_prefix() + ["blame", "-L", f"{lineno},{lineno}", filepath]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )
        first_line = result.stdout.splitlines()[0] if result.stdout else ""
        if first_line:
            parts = first_line.split()
            if parts and len(parts[0]) >= 8:
                return parts[0]
        return None
    except (subprocess.CalledProcessError, FileNotFoundError, IndexError):
        return None


def _get_line_diff(filepath: str, lineno: int, commit_sha: str) -> str | None:
    """Get the diff for the commit that modified a specific line."""
    try:
        result = subprocess.run(
            ["git", "diff", f"{commit_sha}~1..{commit_sha}", "--", filepath],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None


def _highlight_line_in_diff(diff_text: str, target_lineno: int) -> str:
    """Add context highlighting to show which line in the diff we're interested in."""
    lines = diff_text.splitlines()
    output_lines = []
    in_hunk = False
    current_new_line = 0

    for line in lines:
        if line.startswith("@@"):
            in_hunk = True
            parts = line.split()
            if len(parts) >= 3:
                new_info = parts[2]
                if new_info.startswith("+"):
                    try:
                        parts_new = new_info[1:].split(",")
                        current_new_line = int(parts_new[0])
                    except (ValueError, IndexError):
                        current_new_line = 0
            output_lines.append(line)
        elif in_hunk and line.startswith("+"):
            if current_new_line == target_lineno:
                output_lines.append(f">>> {line}  <-- TARGET LINE")
            else:
                output_lines.append(line)
            current_new_line += 1
        elif in_hunk and not line.startswith("-"):
            if line != "":
                if current_new_line == target_lineno:
                    output_lines.append(f">>> {line}  <-- TARGET LINE")
                else:
                    output_lines.append(line)
                current_new_line += 1
            else:
                output_lines.append(line)
        else:
            output_lines.append(line)

    return "\n".join(output_lines)


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
            console.print("[dim]Hint: run devmemory sync first[/dim]")
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
    show_diff: bool = typer.Option(False, "--diff", "-d", help="Show git diff for the line"),
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
            result = storage.get_attribution(ns, filepath, commit_sha, lineno)
            if not result:
                console.print(f"[red]No attribution found for {filepath}:{lineno}@{commit_sha[:8]}[/red]")
                raise typer.Exit(1)
        else:
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
            console.print("[green]✓ AI-generated[/green]")
        else:
            console.print("[yellow]Human-written[/yellow]")

        if result.get("tool"):
            console.print(f"[bold]Tool:[/bold] {result['tool']}")
        if result.get("model"):
            console.print(f"[bold]Model:[/bold] {result['model']}")
        if result.get("prompt_id"):
            console.print(f"[bold]Prompt ID:[/bold] {result['prompt_id']}")
        if result.get("author_email"):
            console.print(f"[bold]Author:[/bold] {result['author_email']}")
        console.print(f"[bold]Confidence:[/bold] {result.get('confidence', 0.95)}")

        if show_diff:
            console.print(f"\n[bold cyan]═══ Git Diff for Line {lineno} ═══[/bold cyan]")

            blame_commit = _get_blame_commit(filepath, lineno)
            if not blame_commit:
                console.print("[yellow]⚠ Could not determine commit for this line[/yellow]")
                raise typer.Exit(0)

            console.print(f"[dim]Commit that modified line {lineno}: {blame_commit[:8]}[/dim]")

            diff_text = _get_line_diff(filepath, lineno, blame_commit)
            if not diff_text:
                console.print("[yellow]⚠ Could not get diff for this commit[/yellow]")
                raise typer.Exit(0)

            highlighted_diff = _highlight_line_in_diff(diff_text, lineno)

            syntax = Syntax(highlighted_diff, "diff", theme="monokai", line_numbers=False)
            console.print(syntax)

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

    conn = storage._get_conn()

    cursor = conn.execute(
        "SELECT commit_sha, commit_timestamp FROM attributions WHERE namespace = ? AND filepath = ? GROUP BY commit_sha ORDER BY commit_timestamp DESC LIMIT ?",
        (ns, filepath, limit),
    )
    rows = cursor.fetchall()

    if not rows:
        console.print(f"[yellow]No attribution data found for {filepath}[/yellow]")
        raise typer.Exit(0)

    commits = []
    for row in rows:
        cursor = conn.execute(
            "SELECT COUNT(*) FROM attributions WHERE namespace = ? AND filepath = ? AND commit_sha = ?",
            (ns, filepath, row[0]),
        )
        range_count = cursor.fetchone()[0]
        commits.append(
            {
                "commit_sha": row[0],
                "timestamp": row[1],
                "ranges": range_count,
            }
        )

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

        if timestamp:
            dt = datetime.fromtimestamp(timestamp)
            date_str = dt.strftime("%Y-%m-%d %H:%M")
        else:
            date_str = "unknown"

        table.add_row(commit_sha[:8], date_str, str(range_count))

    console.print(table)


if __name__ == "__main__":
    attribution_app()
