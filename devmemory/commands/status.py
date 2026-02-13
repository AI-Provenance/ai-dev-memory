import pathlib

from rich.console import Console
from rich.table import Table

from devmemory.core.config import DevMemoryConfig
from devmemory.core.sync_state import SyncState
from devmemory.core.git_ai_parser import get_repo_root, get_git_ai_version, is_git_ai_installed
from devmemory.core.ams_client import AMSClient
from devmemory import __version__

console = Console()


def run_status():
    config = DevMemoryConfig.load()

    table = Table(title="DevMemory Status", show_header=False, border_style="dim")
    table.add_column("Key", style="bold")
    table.add_column("Value")

    table.add_row("DevMemory version", __version__)

    git_ai_ok = is_git_ai_installed()
    git_ai_ver = get_git_ai_version() if git_ai_ok else "not installed"
    table.add_row("Git AI", f"[green]{git_ai_ver}[/green]" if git_ai_ok else "[red]not installed[/red]")

    repo_root = get_repo_root()
    table.add_row("Git repo", repo_root or "[red]not in a git repo[/red]")

    client = AMSClient(base_url=config.ams_endpoint)
    try:
        health = client.health_check()
        ams_status = f"[green]healthy[/green] (endpoint: {config.ams_endpoint})"
    except Exception:
        health = None
        ams_status = f"[red]unreachable[/red] (endpoint: {config.ams_endpoint})"
    table.add_row("AMS server", ams_status)

    if health:
        count = client.get_memory_count(namespace=config.namespace)
        table.add_row("Memories stored", str(count) if count >= 0 else "[yellow]unknown[/yellow]")
    else:
        table.add_row("Memories stored", "[dim]N/A[/dim]")

    table.add_row("Namespace", config.namespace)
    table.add_row("User ID", config.user_id or "[dim]auto (from git)[/dim]")

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

    mcp_config = pathlib.Path.home() / ".cursor" / "mcp.json"
    if mcp_config.exists() and "agent-memory" in mcp_config.read_text():
        table.add_row("Cursor MCP config", "[green]configured[/green]")
    else:
        table.add_row("Cursor MCP config", "[yellow]not configured[/yellow] (run: devmemory install)")

    console.print(table)
