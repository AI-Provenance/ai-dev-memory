import typer
from rich.console import Console
from rich.table import Table

from devmemory.core.config import DevMemoryConfig
from devmemory.core.sync_state import SyncState
from devmemory.core.git_ai_parser import (
    get_repo_root,
    get_ai_notes_since,
    get_latest_commit_note,
)
from devmemory.core.memory_formatter import format_commit_as_memories, format_commit_without_ai
from devmemory.core.ams_client import AMSClient

console = Console()


def run_sync(
    latest: bool = False,
    all_commits: bool = False,
    ai_only: bool = True,
    dry_run: bool = False,
    limit: int = 50,
    quiet: bool = False,
):
    repo_root = get_repo_root()
    if not repo_root:
        if not quiet:
            console.print("[red]Not inside a git repository.[/red]")
        raise typer.Exit(1)

    config = DevMemoryConfig.load()
    state = SyncState.load(repo_root)

    if latest:
        note = get_latest_commit_note()
        if not note:
            if not quiet:
                console.print("[yellow]No commits found.[/yellow]")
            raise typer.Exit(0)
        notes = [note]
    else:
        since_sha = None if all_commits else (state.last_synced_sha or None)
        notes = get_ai_notes_since(since_sha, limit=limit)

    if not notes:
        if not quiet:
            console.print("[green]Already up to date. No new commits to sync.[/green]")
        raise typer.Exit(0)

    if ai_only:
        ai_notes = [n for n in notes if n.has_ai_note]
        skipped = len(notes) - len(ai_notes)
        if skipped > 0 and not quiet:
            console.print(f"[dim]Skipping {skipped} commit(s) without AI notes.[/dim]")
        notes_to_sync = ai_notes
    else:
        notes_to_sync = notes

    if not notes_to_sync:
        if not quiet:
            console.print("[green]No commits with AI notes to sync.[/green]")
        if notes:
            state.mark_synced(notes[0].sha, count=0)
        raise typer.Exit(0)

    if not quiet:
        table = Table(title=f"Commits to sync ({len(notes_to_sync)})")
        table.add_column("SHA", style="cyan", width=12)
        table.add_column("Subject", style="white")
        table.add_column("AI Files", style="green", justify="right")
        table.add_column("Prompts", style="magenta", justify="right")
        table.add_column("Author", style="dim")

        for n in notes_to_sync:
            table.add_row(
                n.sha[:12],
                n.subject[:60],
                str(len(n.files)),
                str(len(n.prompts)),
                n.author_name,
            )
        console.print(table)

    if dry_run:
        if not quiet:
            console.print("[yellow]Dry run -- no memories sent.[/yellow]")
        raise typer.Exit(0)

    client = AMSClient(base_url=config.ams_endpoint)

    try:
        client.health_check()
    except Exception as e:
        if not quiet:
            console.print(f"[red]Cannot reach AMS at {config.ams_endpoint}: {e}[/red]")
            console.print("[dim]Is the Docker stack running? Try: make up[/dim]")
        raise typer.Exit(1)

    total_memories = 0
    for n in notes_to_sync:
        if n.has_ai_note:
            memories = format_commit_as_memories(n, namespace=config.namespace, user_id=config.user_id)
        else:
            memories = format_commit_without_ai(n, namespace=config.namespace, user_id=config.user_id)

        if memories:
            try:
                client.create_memories(memories)
                total_memories += len(memories)
                if not quiet:
                    console.print(f"  [green]✓[/green] {n.sha[:12]} → {len(memories)} memory(s)")
            except Exception as e:
                if not quiet:
                    console.print(f"  [red]✗[/red] {n.sha[:12]} → error: {e}")

    newest_sha = notes_to_sync[0].sha
    state.mark_synced(newest_sha, count=total_memories)

    if quiet:
        if total_memories > 0:
            print(f"devmemory: synced {total_memories} memory(s) from {len(notes_to_sync)} commit(s)")
    else:
        console.print(f"\n[green]Synced {total_memories} memories from {len(notes_to_sync)} commit(s).[/green]")
        console.print(f"[dim]Last synced: {newest_sha[:12]}[/dim]")
