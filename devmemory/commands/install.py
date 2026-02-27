import json
import stat
import importlib.resources
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

RULE_FILENAME = "devmemory.mdc"
CONTEXT_RULE_FILENAME = "devmemory-context.mdc"
COLD_START_RULE_FILENAME = "devmemory-cold-start.mdc"
UNIVERSAL_RULE_FILENAME = "universal-agent-coordination.mdc"

CHECKOUT_HOOK_MARKER = "# >>> devmemory post-checkout hook >>>"
CHECKOUT_HOOK_END = "# <<< devmemory post-checkout hook <<<"

CHECKOUT_HOOK_SCRIPT = f"""{CHECKOUT_HOOK_MARKER}
(devmemory context --quiet 2>/dev/null) &
{CHECKOUT_HOOK_END}"""


def _install_post_commit_hook(repo_root: str) -> bool:
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


def _install_single_rule(repo_root: str, filename: str) -> bool:
    rules_dir = Path(repo_root) / ".cursor" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    rule_dest = rules_dir / filename

    rule_source = Path(__file__).resolve().parent.parent / "rules" / filename
    if not rule_source.exists():
        return False

    rule_content = rule_source.read_text()

    # Template replacement
    if "{{NAMESPACE}}" in rule_content:
        config = DevMemoryConfig.load()
        ns = config.get_active_namespace()
        rule_content = rule_content.replace("{{NAMESPACE}}", ns)

    if rule_dest.exists():
        existing = rule_dest.read_text()
        if existing == rule_content:
            return True

    rule_dest.write_text(rule_content)
    return True


def _install_cursor_rules(repo_root: str) -> tuple[bool, bool, bool, bool]:
    main_ok = _install_single_rule(repo_root, RULE_FILENAME)
    context_ok = _install_single_rule(repo_root, CONTEXT_RULE_FILENAME)
    cold_start_ok = _install_single_rule(repo_root, COLD_START_RULE_FILENAME)
    universal_ok = _install_single_rule(repo_root, UNIVERSAL_RULE_FILENAME)
    return main_ok, context_ok, cold_start_ok, universal_ok


def _install_skills_for_agent(agent_skills_dir: Path) -> tuple[bool, int]:
    repo_skills_dir = Path(__file__).resolve().parent.parent / "skills"
    if not repo_skills_dir.exists():
        return False, 0

    config = DevMemoryConfig.load()
    ns = config.get_active_namespace()

    skills_installed = 0
    for skill_dir in repo_skills_dir.iterdir():
        if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists():
            dest_dir = agent_skills_dir / skill_dir.name
            dest_dir.mkdir(parents=True, exist_ok=True)

            skill_content = (skill_dir / "SKILL.md").read_text()
            if "{{NAMESPACE}}" in skill_content:
                skill_content = skill_content.replace("{{NAMESPACE}}", ns)

            dest_file = dest_dir / "SKILL.md"
            if dest_file.exists():
                existing = dest_file.read_text()
                if existing == skill_content:
                    skills_installed += 1
                    continue

            dest_file.write_text(skill_content)
            skills_installed += 1

    return True, skills_installed


def _install_claude_skills() -> tuple[bool, int]:
    claude_skills_dir = Path.home() / ".claude" / "skills"
    return _install_skills_for_agent(claude_skills_dir)


def _install_antigravity_skills() -> tuple[bool, int]:
    antigravity_skills_dir = Path.home() / ".gemini" / "antigravity" / "skills"
    return _install_skills_for_agent(antigravity_skills_dir)


def _install_cursor_mcp_config(mcp_endpoint: str) -> bool:
    cursor_dir = Path.home() / ".cursor"
    cursor_dir.mkdir(parents=True, exist_ok=True)
    mcp_path = cursor_dir / "mcp.json"

    config_entry = {"url": f"{mcp_endpoint}/sse"}

    if mcp_path.exists():
        try:
            existing = json.loads(mcp_path.read_text())
        except (json.JSONDecodeError, ValueError):
            existing = {}
    else:
        existing = {}

    servers = existing.get("mcpServers")
    if not isinstance(servers, dict):
        servers = {}
    servers["agent-memory"] = config_entry
    existing["mcpServers"] = servers

    mcp_path.write_text(json.dumps(existing, indent=2) + "\n")
    return True


def _install_antigravity_mcp_config(mcp_endpoint: str) -> bool:
    antigravity_dir = Path.home() / ".gemini" / "antigravity"
    antigravity_dir.mkdir(parents=True, exist_ok=True)
    mcp_path = antigravity_dir / "mcp_config.json"

    config_entry = {"url": f"{mcp_endpoint}/sse"}

    if mcp_path.exists():
        try:
            content = mcp_path.read_text().strip()
            existing = json.loads(content) if content else {}
        except (json.JSONDecodeError, ValueError):
            existing = {}
    else:
        existing = {}

    servers = existing.get("mcpServers")
    if not isinstance(servers, dict):
        servers = {}
    servers["agent-memory"] = config_entry
    existing["mcpServers"] = servers

    mcp_path.write_text(json.dumps(existing, indent=2) + "\n")
    return True


def _install_opencode_mcp_config(mcp_endpoint: str) -> bool:
    opencode_dir = Path.home() / ".config" / "opencode"
    opencode_dir.mkdir(parents=True, exist_ok=True)
    config_path = opencode_dir / "opencode.json"

    config_entry = {
        "type": "remote",
        "url": f"{mcp_endpoint}/sse",
        "enabled": True,
    }

    if config_path.exists():
        try:
            content = config_path.read_text().strip()
            existing = json.loads(content) if content else {}
        except (json.JSONDecodeError, ValueError):
            existing = {}
    else:
        existing = {}

    servers = existing.get("mcp")
    if not isinstance(servers, dict):
        servers = {}
    servers["agent-memory"] = config_entry
    existing["mcp"] = servers

    config_path.write_text(json.dumps(existing, indent=2) + "\n")
    return True


def _install_opencode_skills() -> tuple[bool, int]:
    opencode_skills_dir = Path.home() / ".config" / "opencode" / "skills"
    return _install_skills_for_agent(opencode_skills_dir)


def _create_sqlite_database(sqlite_path: str) -> bool:
    """Create SQLite database for local mode attribution storage."""
    try:
        import sqlite3

        # Ensure directory exists
        db_dir = Path(sqlite_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)

        # Create and initialize database
        conn = sqlite3.connect(sqlite_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys = ON")

        # Create attributions table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS attributions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                namespace TEXT NOT NULL,
                filepath TEXT NOT NULL,
                commit_sha TEXT NOT NULL,
                author_email TEXT,
                line_start INTEGER NOT NULL,
                line_end INTEGER NOT NULL,
                author TEXT NOT NULL,
                tool TEXT,
                model TEXT,
                prompt_id TEXT,
                confidence REAL DEFAULT 0.95,
                commit_timestamp INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(namespace, filepath, commit_sha, line_start, line_end)
            )
        """)

        # Create file_latest table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS file_latest (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                namespace TEXT NOT NULL,
                filepath TEXT NOT NULL,
                commit_sha TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(namespace, filepath)
            )
        """)

        # Create indexes
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_attributions_lookup 
            ON attributions(namespace, filepath, commit_sha, line_start, line_end)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_attributions_namespace_filepath 
            ON attributions(namespace, filepath)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_attributions_commit_sha 
            ON attributions(commit_sha)
        """)

        conn.commit()
        conn.close()
        console.print(f"[green]✓[/green] SQLite database created at {sqlite_path}")
        return True

    except Exception as e:
        console.print(f"[red]✗[/red] Failed to create SQLite database: {e}")
        return False


def _ask_for_mode() -> str:
    """Ask user to select installation mode."""
    console.print("\n[bold]Select Installation Mode:[/bold]\n")
    console.print("  [1] [cyan]Local[/cyan] - SQLite only (no external dependencies)")
    console.print("      - Code line attributions stored locally in SQLite")
    console.print("      - No Redis or AMS required")
    console.print("      - Works offline")
    console.print("      - Great for personal projects and debugging\n")
    console.print("  [2] [cyan]Cloud[/cyan] - Redis + AMS (full features)")
    console.print("      - All features including semantic search")
    console.print("      - MCP integration for Cursor/VS Code")
    console.print("      - Agent skills for Claude/OpenCode")
    console.print("      - Team collaboration features\n")

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
    skip_cursor: bool = False,
    skip_antigravity: bool = False,
    skip_opencode: bool = False,
    skip_rule: bool = False,
    skip_skills: bool = False,
    mcp_endpoint: str = "",
    interactive: bool = False,
    force_mode: str = "",
):
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
        # Default to cloud mode for non-interactive
        mode = config.installation_mode or "cloud"

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
            console.print("[green]✓[/green] Git AI prompt_storage set to notes (prompts in git notes for DevMemory)")
        if install_git_ai_hooks():
            console.print("[green]✓[/green] Git AI hooks installed (to capture prompts/stats)")
        else:
            console.print(
                "[yellow]![/yellow] Failed to install Git AI hooks (manual: [cyan]git-ai install-hooks[/cyan])"
            )
    else:
        console.print("[yellow]![/yellow] Git AI is not installed")
        console.print("  Install it with: [cyan]curl -sSL https://usegitai.com/install.sh | bash[/cyan]")

    # Install components based on mode
    if mode == "local":
        # Local mode: Only install hooks and SQLite
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
            else:
                console.print("[yellow]![/yellow] SQLite database creation failed, will use default path")

        # Save config
        config.save(local=True)
        console.print(f"[green]✓[/green] Config saved with mode: {mode}")

        console.print("\n[bold green]Local installation complete![/bold green]")
        console.print("Next steps:")
        console.print("  1. Configure Sentry (see below)")
        console.print("  2. Run: [cyan]devmemory sync[/cyan] to sync attributions")
        console.print("  3. Commits will automatically sync attribution data")

        # Show Sentry setup instructions
        console.print("\n[bold]Sentry Setup (Local Mode):[/bold]")
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
        # Cloud mode: Full installation (existing behavior)
        console.print("\n[bold]Cloud Mode Installation:[/bold]\n")

        if not skip_hook:
            if _install_post_commit_hook(repo_root):
                console.print("[green]✓[/green] Post-commit hook installed")
            else:
                console.print("[red]✗[/red] Failed to install post-commit hook")
            if _install_post_checkout_hook(repo_root):
                console.print("[green]✓[/green] Post-checkout hook installed (auto-refreshes context)")
            else:
                console.print("[red]✗[/red] Failed to install post-checkout hook")
        else:
            console.print("[dim]─[/dim] Git hooks skipped")

        endpoint = mcp_endpoint or config.mcp_endpoint
        if not skip_cursor:
            if _install_cursor_mcp_config(endpoint):
                console.print(f"[green]✓[/green] Cursor MCP config written (~/.cursor/mcp.json)")
                console.print(f"  [dim]MCP endpoint: {endpoint}/sse[/dim]")
            else:
                console.print("[red]✗[/red] Failed to write Cursor MCP config")
        else:
            console.print("[dim]─[/dim] Cursor MCP config skipped")

        if not skip_antigravity:
            if _install_antigravity_mcp_config(endpoint):
                console.print(
                    f"[green]✓[/green] Antigravity MCP config written (~/.gemini/antigravity/mcp_config.json)"
                )
                console.print(f"  [dim]MCP endpoint: {endpoint}/sse[/dim]")
            else:
                console.print("[red]✗[/red] Failed to write Antigravity MCP config")
        else:
            console.print("[dim]─[/dim] Antigravity MCP config skipped")

        if not skip_opencode:
            if _install_opencode_mcp_config(endpoint):
                console.print(f"[green]✓[/green] OpenCode MCP config written (~/.config/opencode/opencode.json)")
                console.print(f"  [dim]MCP endpoint: {endpoint}/sse[/dim]")
            else:
                console.print("[red]✗[/red] Failed to write OpenCode MCP config")
        else:
            console.print("[dim]─[/dim] OpenCode MCP config skipped")

        if not skip_rule:
            main_ok, context_ok, cold_start_ok, universal_ok = _install_cursor_rules(repo_root)
            if main_ok:
                console.print(f"[green]✓[/green] Cursor rule installed (.cursor/rules/{RULE_FILENAME})")
            else:
                console.print(f"[red]✗[/red] Failed to install Cursor rule ({RULE_FILENAME})")
            if context_ok:
                console.print(f"[green]✓[/green] Context rule installed (.cursor/rules/{CONTEXT_RULE_FILENAME})")
            else:
                console.print(f"[red]✗[/red] Failed to install context rule ({CONTEXT_RULE_FILENAME})")
            if cold_start_ok:
                console.print(f"[green]✓[/green] Cold-start rule installed (.cursor/rules/{COLD_START_RULE_FILENAME})")
            else:
                console.print(f"[red]✗[/red] Failed to install cold-start rule ({COLD_START_RULE_FILENAME})")
            if universal_ok:
                console.print(
                    f"[green]✓[/green] Universal agent rule installed (.cursor/rules/{UNIVERSAL_RULE_FILENAME})"
                )
            else:
                console.print(f"[red]✗[/red] Failed to install universal rule ({UNIVERSAL_RULE_FILENAME})")
        else:
            console.print("[dim]─[/dim] Cursor rules skipped")

        if not skip_skills:
            claude_ok, claude_count = _install_claude_skills()
            if claude_ok:
                console.print(f"[green]✓[/green] Claude skills installed ({claude_count} skills in ~/.claude/skills/)")
            else:
                console.print("[yellow]![/yellow] Failed to install Claude skills")

            anti_ok, anti_count = _install_antigravity_skills()
            if anti_ok:
                console.print(
                    f"[green]✓[/green] Antigravity skills installed ({anti_count} skills in ~/.gemini/antigravity/skills/)"
                )
            else:
                console.print("[yellow]![/yellow] Failed to install Antigravity skills")

            opencode_ok, opencode_count = _install_opencode_skills()
            if opencode_ok:
                console.print(
                    f"[green]✓[/green] OpenCode skills installed ({opencode_count} skills in ~/.config/opencode/skills/)"
                )
            else:
                console.print("[yellow]![/yellow] Failed to install OpenCode skills")
        else:
            console.print("[dim]─[/dim] Agent skills skipped")

        # Save config
        config.save(local=True)
        console.print(f"[green]✓[/green] Config saved with mode: {mode}")

        if not config.user_id:
            console.print("\n[dim]Tip: Set your user ID for better memory attribution:[/dim]")
            console.print("  [cyan]devmemory config set user_id your@email.com[/cyan]")

        console.print("\n[bold green]Installation complete![/bold green]")
        console.print("Next steps:")
        console.print("  1. Start the stack: [cyan]make up[/cyan]")
        console.print("  2. Check status:    [cyan]devmemory status[/cyan]")
        console.print("  3. Make a commit and watch memories sync automatically")
