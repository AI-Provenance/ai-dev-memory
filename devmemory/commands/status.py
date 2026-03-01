import pathlib

from rich.console import Console
from rich.table import Table

from devmemory.core.config import DevMemoryConfig
from devmemory.core.sync_state import SyncState
from devmemory.core.git_ai_parser import get_git_ai_version, is_git_ai_installed, get_repo_stats
from devmemory.core.utils import get_repo_root
from devmemory import __version__

console = Console()


def run_status():
    config = DevMemoryConfig.load()
    is_local_mode = config.installation_mode == "local"

    if is_local_mode:
        _run_status_local(config)
    else:
        _run_status_cloud(config)


def _run_status_local(config: DevMemoryConfig):
    from devmemory.attribution.sqlite_storage import SQLiteAttributionStorage

    local_console = Console()

    table = Table(title="DevMemory Status (Local Mode)", show_header=False, border_style="dim")
    table.add_column("Key", style="bold")
    table.add_column("Value")

    table.add_row("DevMemory version", __version__)
    table.add_row("Mode", "[cyan]local[/cyan] (SQLite)")

    repo_root = get_repo_root()
    table.add_row("Git repo", repo_root or "[red]not in a git repo[/red]")

    git_ai_ok = is_git_ai_installed()
    git_ai_ver = get_git_ai_version() if git_ai_ok else "not installed"
    table.add_row("Git AI", f"[green]{git_ai_ver}[/green]" if git_ai_ok else "[red]not installed[/red]")

    if git_ai_ok and repo_root:
        repo_stats = get_repo_stats(all_branches=False)
        if repo_stats.total_commits > 0:
            ai_pct = repo_stats.ai_percentage
            human_pct = repo_stats.human_percentage
            if repo_stats.ai_commits > 0:
                stats_str = f"[green]{human_pct:.0f}%[/green] Human, [cyan]{ai_pct:.0f}%[/cyan] AI ({repo_stats.ai_commits} AI commits)"
            else:
                stats_str = (
                    f"[green]{human_pct:.0f}%[/green] Human, [cyan]{ai_pct:.0f}%[/cyan] AI (no AI-assisted commits)"
                )
            table.add_row("Code stats", stats_str)

    sqlite_path = config.sqlite_path
    if sqlite_path:
        db_path = pathlib.Path(sqlite_path)
        if db_path.exists():
            try:
                storage = SQLiteAttributionStorage(sqlite_path)
                count = storage.get_attribution_count()
                storage.close()
                table.add_row("Attributions", f"[green]{count}[/green] records")
            except Exception:
                table.add_row("Attributions", "[red]error reading database[/red]")
        else:
            table.add_row("Attributions", "[yellow]database not found[/yellow]")
    else:
        table.add_row("Attributions", "[yellow]not configured[/yellow]")

    if repo_root:
        state = SyncState.load(repo_root)
        if state.last_synced_sha:
            table.add_row("Last synced commit", state.last_synced_sha[:12])
            table.add_row("Last synced at", state.last_synced_at)
            table.add_row("Total synced", str(state.total_synced))
        else:
            table.add_row("Sync state", "[yellow]never synced[/yellow]")

    hook_path = pathlib.Path(repo_root) / ".git" / "hooks" / "post-commit" if repo_root else None
    if hook_path and hook_path.exists() and "devmemory" in hook_path.read_text():
        table.add_row("Post-commit hook", "[green]installed[/green]")
    else:
        table.add_row("Post-commit hook", "[yellow]not installed[/yellow] (run: devmemory install)")

    local_console.print(table)


def _run_status_cloud(config: DevMemoryConfig):
    """Cloud mode status - API-based."""
    local_console = Console()

    table = Table(title="DevMemory Status (Cloud Mode)", show_header=False, border_style="dim")
    table.add_column("Key", style="bold")
    table.add_column("Value")

    table.add_row("DevMemory version", __version__)
    table.add_row("Mode", "[cyan]cloud[/cyan] (API-based)")

    repo_root = get_repo_root()
    table.add_row("Git repo", repo_root or "[red]not in a git repo[/red]")

    git_ai_ok = is_git_ai_installed()
    git_ai_ver = get_git_ai_version() if git_ai_ok else "not installed"
    table.add_row("Git AI", f"[green]{git_ai_ver}[/green]" if git_ai_ok else "[red]not installed[/red]")

    if git_ai_ok and repo_root:
        repo_stats = get_repo_stats(all_branches=False)
        if repo_stats.total_commits > 0:
            ai_pct = repo_stats.ai_percentage
            human_pct = repo_stats.human_percentage
            if repo_stats.ai_commits > 0:
                stats_str = f"[green]{human_pct:.0f}%[/green] Human, [cyan]{ai_pct:.0f}%[/cyan] AI ({repo_stats.ai_commits} AI commits)"
            else:
                stats_str = (
                    f"[green]{human_pct:.0f}%[/green] Human, [cyan]{ai_pct:.0f}%[/cyan] AI (no AI-assisted commits)"
                )
            table.add_row("Code stats", stats_str)

    # API Key status
    if config.api_key:
        masked_key = config.api_key[:8] + "..." if len(config.api_key) > 8 else "***"
        table.add_row("API Key", f"[green]configured[/green] ({masked_key})")
    else:
        table.add_row("API Key", "[red]not configured[/red] (run: devmemory config set api_key YOUR_KEY)")

    table.add_row("API Endpoint", "https://api.aiprove.org")

    # Local SQLite (used for caching/offline)
    from devmemory.attribution.sqlite_storage import SQLiteAttributionStorage

    sqlite_path = config.sqlite_path
    if sqlite_path:
        db_path = pathlib.Path(sqlite_path)
        if db_path.exists():
            try:
                storage = SQLiteAttributionStorage(sqlite_path)
                count = storage.get_attribution_count()
                storage.close()
                table.add_row("Local attributions", f"[green]{count}[/green] records (cache)")
            except Exception:
                table.add_row("Local attributions", "[red]error reading database[/red]")
        else:
            table.add_row("Local attributions", "[yellow]database not found[/yellow]")
    else:
        table.add_row("Local attributions", "[yellow]not configured[/yellow]")

    if repo_root:
        state = SyncState.load(repo_root)
        if state.last_synced_sha:
            table.add_row("Last synced commit", state.last_synced_sha[:12])
            table.add_row("Last synced at", state.last_synced_at)
            table.add_row("Total synced", str(state.total_synced))
        else:
            table.add_row("Sync state", "[yellow]never synced[/yellow]")

    if repo_root:
        hook_path = pathlib.Path(repo_root) / ".git" / "hooks" / "post-commit"
        if hook_path.exists() and "devmemory" in hook_path.read_text():
            table.add_row("Post-commit hook", "[green]installed[/green]")
        else:
            table.add_row("Post-commit hook", "[yellow]not installed[/yellow] (run: devmemory install)")

    # Note about cloud features
    table.add_row("", "")
    if config.api_key:
        table.add_row("Cloud features", "[dim]Ready to use (API available)[/dim]")
    else:
        table.add_row("Cloud features", "[yellow]API key required[/yellow] (get one at aiprove.org)")

    local_console.print(table)
