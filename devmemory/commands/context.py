"""Context command for DevMemory.

This module generates context briefings from memory based on current git state.
All business logic is handled by the Cloud API.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import typer
from rich.console import Console

from devmemory.core.config import DevMemoryConfig
from devmemory.attribution.cloud_storage import CloudStorage

console = Console()

DEFAULT_OUTPUT = ".devmemory/CONTEXT.md"


def _git_cmd(args: list[str]) -> str:
    """Run a git command and return output."""
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def _get_git_signals() -> dict:
    """Collect git signals for context generation."""
    branch = _git_cmd(["rev-parse", "--abbrev-ref", "HEAD"])

    changed_raw = _git_cmd(["diff", "--name-only"])
    staged_raw = _git_cmd(["diff", "--cached", "--name-only"])
    all_changed = set()
    if changed_raw:
        all_changed.update(changed_raw.splitlines())
    if staged_raw:
        all_changed.update(staged_raw.splitlines())

    recent_log = _git_cmd(["log", "--oneline", "-5", "--format=%s"])
    recent_subjects = [s.strip() for s in recent_log.splitlines() if s.strip()] if recent_log else []

    recent_files_raw = _git_cmd(["log", "--name-only", "--format=", "-3"])
    recent_files = set()
    if recent_files_raw:
        for f in recent_files_raw.splitlines():
            f = f.strip()
            if f:
                recent_files.add(f)

    return {
        "branch": branch or "unknown",
        "changed_files": sorted(all_changed),
        "recent_subjects": recent_subjects,
        "recent_files": sorted(recent_files),
    }


def run_context(
    output: str = "",
    quiet: bool = False,
):
    """Generate a context briefing from memory based on current git state."""

    config = DevMemoryConfig.load()

    if not quiet:
        console.print("[dim]Collecting git signals...[/dim]")

    signals = _get_git_signals()
    output_path = output or DEFAULT_OUTPUT

    with CloudStorage(api_key=config.api_key) as client:
        result = client.generate_context(output=output_path, quiet=quiet)

        if result.get("error"):
            if not quiet:
                console.print(f"[yellow]Cloud API unavailable - generating local context from git signals.[/yellow]")
            _generate_local_context(signals, output_path, quiet)
            return

        if not quiet:
            console.print(f"[green]Context generated: {result.get('data', {}).get('output_path', output_path)}[/green]")


def _generate_local_context(signals: dict, output: str, quiet: bool):
    """Generate context locally from git signals when API is unavailable."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    parts = [
        f"# DevMemory Context",
        f"_Auto-generated at {now}. Run `devmemory context` to refresh._\n",
    ]

    parts.append(f"## Current Branch: `{signals['branch']}`\n")

    if signals["changed_files"]:
        parts.append("## Active Changes\n")
        for f in signals["changed_files"][:15]:
            parts.append(f"- `{f}`")
        if len(signals["changed_files"]) > 15:
            parts.append(f"- ... and {len(signals['changed_files']) - 15} more")
        parts.append("")

    if signals["recent_subjects"]:
        parts.append("## Recent Commits\n")
        for s in signals["recent_subjects"]:
            parts.append(f"- {s}")
        parts.append("")

    parts.append("## No Relevant Memories Found\n")
    parts.append("No memories matched the current work area. Cloud API may be unavailable.")
    parts.append('Use `devmemory search "<query>"` for broader searches.')
    parts.append("")

    parts.append("---")
    parts.append(f"_Generated from git signals only._")

    content = "\n".join(parts)
    _write_output(content, output, quiet)


def _write_output(content: str, output: str, quiet: bool):
    """Write context to file."""
    out_path = Path(output) if output else Path.cwd() / DEFAULT_OUTPUT
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content)
    if not quiet:
        console.print(f"[dim]Written to {out_path}[/dim]")
