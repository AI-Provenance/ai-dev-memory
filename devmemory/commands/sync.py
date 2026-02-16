import typer
from rich.console import Console
from rich.table import Table

from devmemory.core.config import DevMemoryConfig
from devmemory.core.sync_state import SyncState
from devmemory.core.git_ai_parser import (
    get_ai_notes_since,
    get_latest_commit_note,
)
from devmemory.core.utils import get_repo_root
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
    batch_size: int = 50,
    local_enrichment: bool = True,
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

    client = AMSClient(base_url=config.ams_endpoint)

    try:
        client.health_check()
    except Exception as e:
        if not quiet:
            console.print(f"[red]Cannot reach AMS at {config.ams_endpoint}: {e}[/red]")
            console.print("[dim]Is the Docker stack running? Try: make up[/dim]")
        raise typer.Exit(1)

    if not quiet:
        console.print(f"[bold]Syncing {len(notes_to_sync)} commit(s)...[/bold]")

    all_memories = []
    synced_shas = []

    for n in notes_to_sync:
        if n.has_ai_note:
            memories = format_commit_as_memories(
                n, 
                namespace=config.namespace, 
                user_id=config.user_id,
                local_enrichment=local_enrichment
            )
        else:
            memories = format_commit_without_ai(
                n, 
                namespace=config.namespace, 
                user_id=config.user_id
            )

        if memories:
            all_memories.extend(memories)
            synced_shas.append(n.sha)

    if dry_run:
        if not quiet:
            console.print(f"[yellow]Dry run -- {len(all_memories)} memories would be sent.[/yellow]")
        raise typer.Exit(0)

    total_synced = 0
    if all_memories:
        try:
            with client:
                # Process in batches to avoid huge payloads
                for i in range(0, len(all_memories), batch_size):
                    batch = all_memories[i : i + batch_size]
                    if not quiet:
                        console.print(f"  Sending batch {i//batch_size + 1} ({len(batch)} memories)...", end="\r")
                    client.create_memories(batch)
                    total_synced += len(batch)

            if not quiet:
                console.print(f"\n[green]✓ Successfully synced {total_synced} memories.[/green]")
        except Exception as e:
            if not quiet:
                console.print(f"\n[red]✗ Sync failed: {e}[/red]")
            raise typer.Exit(1)

    newest_sha = notes_to_sync[0].sha
    state.mark_synced(newest_sha, count=total_synced)

    if quiet:
        if total_synced > 0:
            print(f"devmemory: synced {total_synced} memory(s) from {len(notes_to_sync)} commit(s)")
    else:
        console.print(f"[dim]Last synced: {newest_sha[:12]}[/dim]")
