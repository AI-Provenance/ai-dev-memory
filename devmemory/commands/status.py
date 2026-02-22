import pathlib

from rich.console import Console
from rich.table import Table

from devmemory.core.config import DevMemoryConfig
from devmemory.core.sync_state import SyncState
from devmemory.core.git_ai_parser import get_git_ai_version, is_git_ai_installed, get_repo_stats, RepoStats
from devmemory.core.utils import get_repo_root
from devmemory.core.ams_client import AMSClient
from devmemory import __version__

console = Console()

MAIN_RULE_NAME = "devmemory.mdc"
CONTEXT_RULE_NAME = "devmemory-context.mdc"


def get_cursor_rules_status(repo_root: pathlib.Path) -> str:
    main_rule = repo_root / ".cursor" / "rules" / MAIN_RULE_NAME
    context_rule = repo_root / ".cursor" / "rules" / CONTEXT_RULE_NAME

    main_ok = main_rule.exists()
    context_ok = context_rule.exists()

    if main_ok and context_ok:
        try:
            main_content = main_rule.read_text(encoding="utf-8")
            context_content = context_rule.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return "[yellow]rules unreadable or invalid[/yellow] (run: devmemory install)"

        main_always_apply = "alwaysApply: true" in main_content
        main_mcp_refs = "agent-memory" in main_content and "search_long_term_memory" in main_content

        context_always_apply = "alwaysApply: true" in context_content
        context_marker = "CONTEXT.md" in context_content and "devmemory context" in context_content

        if main_always_apply and main_mcp_refs and context_always_apply and context_marker:
            return "[green]installed[/green] (devmemory.mdc, devmemory-context.mdc)"
        if not (context_always_apply and context_marker):
            return "[yellow]context rule outdated or missing required content (alwaysApply, CONTEXT markers)[/yellow] (run: devmemory install)"
        if not (main_always_apply and main_mcp_refs):
            return "[yellow]main rule outdated or missing required content (alwaysApply, MCP refs)[/yellow] (run: devmemory install)"
    if main_ok:
        return "[yellow]partially installed[/yellow] (missing context rule)"
    if context_ok:
        return "[yellow]partially installed[/yellow] (missing main rule)"
    return "[yellow]not installed[/yellow] (run: devmemory install)"


def get_skills_status() -> str:
    claude_skills_dir = pathlib.Path.home() / ".claude" / "skills"
    antigravity_skills_dir = pathlib.Path.home() / ".gemini" / "antigravity" / "skills"

    claude_ok = (claude_skills_dir / "devmemory-memory" / "SKILL.md").exists()
    anti_ok = (antigravity_skills_dir / "devmemory-memory" / "SKILL.md").exists()

    if claude_ok and anti_ok:
        return "[green]installed[/green] (Claude, Antigravity)"
    elif claude_ok:
        return "[yellow]partially installed[/yellow] (Claude only)"
    elif anti_ok:
        return "[yellow]partially installed[/yellow] (Antigravity only)"
    else:
        return "[yellow]not installed[/yellow] (run: devmemory install)"


def run_status():
    config = DevMemoryConfig.load()

    table = Table(title="DevMemory Status", show_header=False, border_style="dim")
    table.add_column("Key", style="bold")
    table.add_column("Value")

    table.add_row("DevMemory version", __version__)

    repo_root = get_repo_root()

    git_ai_ok = is_git_ai_installed()
    git_ai_ver = get_git_ai_version() if git_ai_ok else "not installed"
    table.add_row("Git AI", f"[green]{git_ai_ver}[/green]" if git_ai_ok else "[red]not installed[/red]")

    # Show repo AI vs Human stats if Git AI is installed
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
    table.add_row("Git repo", repo_root or "[red]not in a git repo[/red]")

    client = AMSClient(base_url=config.ams_endpoint, auth_token=config.get_auth_token())
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

    if repo_root:
        table.add_row("Cursor rules", get_cursor_rules_status(pathlib.Path(repo_root)))

    table.add_row("Agent Skills", get_skills_status())

    console.print(table)
