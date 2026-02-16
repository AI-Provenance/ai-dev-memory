import json
import stat
import importlib.resources
from pathlib import Path

import typer
from rich.console import Console

from devmemory.core.config import DevMemoryConfig
from devmemory.core.git_ai_parser import get_repo_root, is_git_ai_installed, enable_prompt_storage_notes, install_git_ai_hooks

console = Console()

HOOK_MARKER = "# >>> devmemory post-commit hook >>>"
HOOK_END = "# <<< devmemory post-commit hook <<<"

HOOK_SCRIPT = f"""{HOOK_MARKER}
(sleep 2 && devmemory sync --latest 2>/dev/null) &
{HOOK_END}"""

RULE_FILENAME = "devmemory.mdc"
CONTEXT_RULE_FILENAME = "devmemory-context.mdc"

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

    if rule_dest.exists():
        existing = rule_dest.read_text()
        if existing == rule_content:
            return True

    rule_dest.write_text(rule_content)
    return True


def _install_cursor_rules(repo_root: str) -> tuple[bool, bool]:
    main_ok = _install_single_rule(repo_root, RULE_FILENAME)
    context_ok = _install_single_rule(repo_root, CONTEXT_RULE_FILENAME)
    return main_ok, context_ok


def _install_cursor_mcp_config(mcp_endpoint: str) -> bool:
    cursor_dir = Path.home() / ".cursor"
    cursor_dir.mkdir(parents=True, exist_ok=True)
    mcp_path = cursor_dir / "mcp.json"

    config_entry = {
        "url": f"{mcp_endpoint}/sse"
    }

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

    config_entry = {
        "url": f"{mcp_endpoint}/sse"
    }

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


def run_install(
    skip_hook: bool = False,
    skip_cursor: bool = False,
    skip_antigravity: bool = False,
    skip_rule: bool = False,
    mcp_endpoint: str = "",
):
    config = DevMemoryConfig.load()
    repo_root = get_repo_root()

    console.print("[bold]DevMemory Installation[/bold]\n")

    git_ai_ok = is_git_ai_installed()
    if git_ai_ok:
        console.print("[green]✓[/green] Git AI is installed")
        if enable_prompt_storage_notes():
            console.print("[green]✓[/green] Git AI prompt_storage set to notes (prompts in git notes for DevMemory)")
        if install_git_ai_hooks():
            console.print("[green]✓[/green] Git AI hooks installed (to capture prompts/stats)")
        else:
            console.print("[yellow]![/yellow] Failed to install Git AI hooks (manual: [cyan]git-ai install-hooks[/cyan])")
    else:
        console.print("[yellow]![/yellow] Git AI is not installed")
        console.print("  Install it with: [cyan]curl -sSL https://usegitai.com/install.sh | bash[/cyan]")

    if not repo_root:
        console.print("[red]✗[/red] Not inside a git repository. Run this from a git repo.")
        raise typer.Exit(1)

    console.print(f"[green]✓[/green] Git repository: {repo_root}")

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
            console.print(f"[green]✓[/green] Antigravity MCP config written (~/.gemini/antigravity/mcp_config.json)")
            console.print(f"  [dim]MCP endpoint: {endpoint}/sse[/dim]")
        else:
            console.print("[red]✗[/red] Failed to write Antigravity MCP config")
    else:
        console.print("[dim]─[/dim] Antigravity MCP config skipped")

    if not skip_rule:
        main_ok, context_ok = _install_cursor_rules(repo_root)
        if main_ok:
            console.print(f"[green]✓[/green] Cursor rule installed (.cursor/rules/{RULE_FILENAME})")
        else:
            console.print(f"[red]✗[/red] Failed to install Cursor rule ({RULE_FILENAME})")
        if context_ok:
            console.print(f"[green]✓[/green] Context rule installed (.cursor/rules/{CONTEXT_RULE_FILENAME})")
        else:
            console.print(f"[red]✗[/red] Failed to install context rule ({CONTEXT_RULE_FILENAME})")
    else:
        console.print("[dim]─[/dim] Cursor rules skipped")

    if not config.user_id:
        console.print("\n[dim]Tip: Set your user ID for better memory attribution:[/dim]")
        console.print("  [cyan]devmemory config set user_id your@email.com[/cyan]")

    console.print("\n[bold green]Installation complete![/bold green]")
    console.print("Next steps:")
    console.print("  1. Start the stack: [cyan]make up[/cyan]")
    console.print("  2. Check status:    [cyan]devmemory status[/cyan]")
    console.print("  3. Make a commit and watch memories sync automatically")
