import json
import stat
from pathlib import Path

import typer
from rich.console import Console

from devmemory.core.config import DevMemoryConfig
from devmemory.core.git_ai_parser import is_git_ai_installed, enable_prompt_storage_notes, install_git_ai_hooks
from devmemory.core.utils import get_repo_root

console = Console()

HOOK_MARKER = "# >>> devmemory post-commit hook >>>"
HOOK_END = "# <<< devmemory post-commit hook <<<"

HOOK_SCRIPT = f"""{HOOK_MARKER}
(sleep 2 && devmemory sync --latest 2>/dev/null) &
{HOOK_END}"""

CHECKOUT_HOOK_MARKER = "# >>> devmemory post-checkout hook >>>"
CHECKOUT_HOOK_END = "# <<< devmemory post-checkout hook <<<"

CHECKOUT_HOOK_SCRIPT = f"""{CHECKOUT_HOOK_MARKER}
(devmemory context --quiet 2>/dev/null) &
{CHECKOUT_HOOK_END}"""


def _install_post_commit_hook(repo_root: str) -> bool:
    """Install post-commit hook to sync attributions after each commit."""
    hooks_dir = Path(repo_root) / ".git" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook_path = hooks_dir / "post-commit"

    if hook_path.exists():
        content = hook_path.read_text()
        if HOOK_MARKER in content:
            console.print("[dim]Post-commit hook already installed, updating...[/dim]")
            start = content.index(HOOK_MARKER)
            end = content.index(HOOK_END) + len(HOOK_END)
            content = content[:start] + HOOK_SCRIPT + content[end:]
            hook_path.write_text(content)
            return True
        else:
            content = content.rstrip() + "\n\n" + HOOK_SCRIPT + "\n"
            hook_path.write_text(content)
            return True
    else:
        hook_path.write_text("#!/bin/bash\n\n" + HOOK_SCRIPT + "\n")

    hook_path.chmod(hook_path.stat().st_mode | stat.S_IEXEC)
    return True


def _install_post_checkout_hook(repo_root: str) -> bool:
    """Install post-checkout hook to refresh context on branch switch."""
    hooks_dir = Path(repo_root) / ".git" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook_path = hooks_dir / "post-checkout"

    if hook_path.exists():
        content = hook_path.read_text()
        if CHECKOUT_HOOK_MARKER in content:
            console.print("[dim]Post-checkout hook already installed, updating...[/dim]")
            start = content.index(CHECKOUT_HOOK_MARKER)
            end = content.index(CHECKOUT_HOOK_END) + len(CHECKOUT_HOOK_END)
            content = content[:start] + CHECKOUT_HOOK_SCRIPT + content[end:]
            hook_path.write_text(content)
            return True
        else:
            content = content.rstrip() + "\n\n" + CHECKOUT_HOOK_SCRIPT + "\n"
            hook_path.write_text(content)
            return True
    else:
        hook_path.write_text("#!/bin/bash\n\n" + CHECKOUT_HOOK_SCRIPT + "\n")

    hook_path.chmod(hook_path.stat().st_mode | stat.S_IEXEC)
    return True


def _create_sqlite_database(sqlite_path: str) -> bool:
    """Create SQLite database for attribution storage."""
    from devmemory.attribution.sqlite_storage import SQLiteAttributionStorage

    try:
        storage = SQLiteAttributionStorage(sqlite_path)
        storage._get_conn()  # Test connection
        storage.close()
        return True
    except Exception as e:
        console.print(f"[yellow]![/yellow] Failed to create SQLite database: {e}")
        return False


def _ask_for_mode() -> str:
    """Interactive mode selection."""
    console.print("\n[bold]Choose installation mode:[/bold]\n")
    console.print("  [cyan]1.[/cyan] Local mode (SQLite, free, works offline)")
    console.print("     • AI code attribution tracking")
    console.print("     • Git hooks for auto-sync")
    console.print("     • Sentry integration")
    console.print("")
    console.print("  [cyan]2.[/cyan] Cloud mode (API-based, advanced features)")
    console.print("     • All local features")
    console.print("     • Semantic search")
    console.print("     • Team analytics")
    console.print("     • Requires API key from aiprove.org")
    console.print("")

    while True:
        choice = console.input("Enter choice (1/2): ").strip()
        if choice == "1":
            return "local"
        elif choice == "2":
            return "cloud"
        else:
            console.print("[yellow]Please enter 1 or 2[/yellow]")


def run_install(
    skip_hook: bool = False,
    interactive: bool = False,
    force_mode: str = "",
    api_key: str = "",
):
    """
    Install DevMemory in the current repository.

    Local mode: SQLite storage, works offline, free forever
    Cloud mode: API-based features (requires API key from aiprove.org)
    """
    config = DevMemoryConfig.load()
    repo_root = get_repo_root()

    console.print("[bold]DevMemory Installation[/bold]\n")

    # Determine installation mode
    if force_mode:
        mode = force_mode
        console.print(f"[cyan]Using specified mode: {mode}[/cyan]\n")
    elif interactive:
        mode = _ask_for_mode()
    else:
        # Default to local mode for non-interactive
        mode = config.installation_mode or "local"

    # Save mode to config
    config.installation_mode = mode

    # Calculate SQLite path
    if mode == "local":
        sqlite_path = config.get_sqlite_path()
    else:
        sqlite_path = ""

    console.print(f"[bold]Mode:[/bold] {mode.upper()}\n")

    if not repo_root:
        console.print("[red]✗[/red] Not inside a git repository. Run this from a git repo.")
        raise typer.Exit(1)

    console.print(f"[green]✓[/green] Git repository: {repo_root}")

    # Git AI check (needed for both modes)
    git_ai_ok = is_git_ai_installed()
    if git_ai_ok:
        console.print("[green]✓[/green] Git AI is installed")
        if enable_prompt_storage_notes():
            console.print("[green]✓[/green] Git AI prompt_storage set to notes")
        if install_git_ai_hooks():
            console.print("[green]✓[/green] Git AI hooks installed")
        else:
            console.print(
                "[yellow]![/yellow] Failed to install Git AI hooks (manual: [cyan]git-ai install-hooks[/cyan])"
            )
    else:
        console.print("[yellow]![/yellow] Git AI is not installed")
        console.print("  Install it with: [cyan]curl -sSL https://usegitai.com/install.sh | bash[/cyan]")

    # Install components
    if mode == "local":
        # Local mode: Install hooks and SQLite
        console.print("\n[bold]Local Mode Installation:[/bold]\n")

        if not skip_hook:
            if _install_post_commit_hook(repo_root):
                console.print("[green]✓[/green] Post-commit hook installed")
            else:
                console.print("[red]✗[/red] Failed to install post-commit hook")
            if _install_post_checkout_hook(repo_root):
                console.print("[green]✓[/green] Post-checkout hook installed")
            else:
                console.print("[red]✗[/red] Failed to install post-checkout hook")
        else:
            console.print("[dim]─[/dim] Git hooks skipped")

        # Create SQLite database
        if sqlite_path:
            if _create_sqlite_database(sqlite_path):
                config.sqlite_path = sqlite_path
                console.print(f"[green]✓[/green] SQLite database created: {sqlite_path}")
            else:
                console.print("[yellow]![/yellow] SQLite database creation failed")

        # Save config
        config.save(local=True)
        console.print(f"[green]✓[/green] Config saved")

        console.print("\n[bold green]Local installation complete![/bold green]")
        console.print("\nNext steps:")
        console.print("  1. Configure Sentry (optional, see docs)")
        console.print("  2. Run: [cyan]devmemory sync[/cyan] to sync attributions")
        console.print("  3. Commits will automatically sync attribution data")

        # Show Sentry setup
        console.print("\n[bold]Sentry Setup:[/bold]")
        console.print("  Add this to your Sentry initialization:")
        console.print("""  [dim]
import sentry_sdk
from devmemory.sentry import create_before_send
                      
sentry_sdk.init(
    dsn="YOUR_SENTRY_DSN",
    before_send=create_before_send(),
    ...
)[/dim]""")

    else:
        # Cloud mode: API-based
        console.print("\n[bold]Cloud Mode Installation:[/bold]\n")
        console.print("Cloud mode uses DevMemory's API for advanced features.\n")

        # Check for API key
        if not api_key:
            console.print("[yellow]⚠ No API key provided[/yellow]")
            console.print("\nTo use cloud mode, you need an API key from aiprove.org")
            console.print("\nOptions:")
            console.print("  1. Get an API key at: https://aiprove.org")
            console.print("  2. Run with --api-key: devmemory install --mode cloud --api-key YOUR_KEY")
            console.print("  3. Use local mode instead: devmemory install --mode local")
            console.print("\n[dim]For now, installing with local mode features only.[/dim]")
            console.print("You can add an API key later with: devmemory config set api_key YOUR_KEY\n")

            # Fall back to local mode
            mode = "local"
            sqlite_path = config.get_sqlite_path()

            if not skip_hook:
                if _install_post_commit_hook(repo_root):
                    console.print("[green]✓[/green] Post-commit hook installed")

            # Create SQLite database
            if sqlite_path:
                if _create_sqlite_database(sqlite_path):
                    config.sqlite_path = sqlite_path
                    console.print(f"[green]✓[/green] SQLite database created: {sqlite_path}")
        else:
            # API key provided
            config.api_key = api_key
            console.print("[green]✓[/green] API key configured")

            # Install hooks
            if not skip_hook:
                if _install_post_commit_hook(repo_root):
                    console.print("[green]✓[/green] Post-commit hook installed")
                if _install_post_checkout_hook(repo_root):
                    console.print("[green]✓[/green] Post-checkout hook installed")

            console.print("\n[green]✓[/green] Cloud mode configured")
            console.print("  API endpoint: https://api.aiprove.org")

        # Save config
        config.save(local=True)
        console.print(f"[green]✓[/green] Config saved with mode: {mode}")

        if not config.user_id:
            console.print("\n[dim]Tip: Set your user ID for better attribution:[/dim]")
            console.print("  [cyan]devmemory config set user_id your@email.com[/cyan]")

        console.print("\n[bold green]Installation complete![/bold green]")

        if mode == "cloud":
            console.print("\nNext steps:")
            console.print("  1. Check status:    [cyan]devmemory status[/cyan]")
            console.print("  2. Make a commit to sync attribution data")
        else:
            console.print("\nLocal mode active. To enable cloud features:")
            console.print("  [cyan]devmemory config set api_key YOUR_API_KEY[/cyan]")
            console.print("  Get your API key at: https://aiprove.org")
