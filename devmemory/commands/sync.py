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
from devmemory.core.memory_formatter import (
    format_commit_as_memories,
    format_commit_without_ai,
    generate_commit_summary,
)
from devmemory.core.ams_client import AMSClient
from devmemory.core.memory_formatter import generate_commit_summary
from datetime import datetime, timezone

console = Console()


def _is_significant_change(notes: list) -> bool:
    """Determine if a batch of commits represents significant changes"""
    if len(notes) < 3:
        return False

    # Check for architectural keywords in commit messages
    architectural_keywords = [
        "refactor",
        "architecture",
        "redesign",
        "migrate",
        "restructure",
        "component",
        "module",
        "interface",
        "contract",
        "protocol",
    ]

    significant_count = 0
    for note in notes:
        subject_lower = note.subject.lower()
        body_lower = note.body.lower() if note.body else ""

        # Check for architectural keywords
        if any(kw in subject_lower or kw in body_lower for kw in architectural_keywords):
            significant_count += 1

        # Check for significant file changes
        if len(note.files) > 5:  # Many files changed
            significant_count += 1

        # Check for AI tool usage (indicates complex changes)
        if note.has_ai_note and len(note.prompts) > 2:
            significant_count += 1

    return significant_count >= 2


def _trigger_auto_summarization(client: AMSClient, config: DevMemoryConfig, state: SyncState, notes: list, quiet: bool):
    """Automatically create project and architecture summaries when significant changes are detected"""

    if not _is_significant_change(notes):
        return

    newest_sha = notes[0].sha
    ns = config.get_active_namespace()

    # Check if we need to create a project summary
    should_create_project = False
    if not state.last_project_summary_sha:
        should_create_project = True
    else:
        # Create project summary every 20 commits or when significant architectural changes
        project_commits_since = _count_commits_since(state.last_project_summary_sha, notes)
        should_create_project = project_commits_since >= 20 or _has_architectural_changes(notes)

    # Check if we need to create an architecture summary
    should_create_architecture = False
    if not state.last_architecture_summary_sha:
        should_create_architecture = True
    else:
        # Create architecture summary every 50 commits or when major architectural changes
        arch_commits_since = _count_commits_since(state.last_architecture_summary_sha, notes)
        should_create_architecture = arch_commits_since >= 50 or _has_major_architectural_changes(notes)

    if not (should_create_project or should_create_architecture):
        return

    if not quiet:
        console.print(f"[dim]Detected significant changes - generating summaries...[/dim]")

    try:
        # Generate project summary
        if should_create_project:
            project_summary = _generate_project_summary_from_commits(notes, ns, config.user_id)
            if project_summary:
                client.create_memories([project_summary])
                state.mark_project_summary(newest_sha)
                if not quiet:
                    console.print(f"[green]✓ Generated project summary for {len(notes)} commits[/green]")

        # Generate architecture summary
        if should_create_architecture:
            arch_summary = _generate_architecture_summary_from_commits(notes, ns, config.user_id)
            if arch_summary:
                client.create_memories([arch_summary])
                state.mark_architecture_summary(newest_sha)
                if not quiet:
                    console.print(f"[green]✓ Generated architecture summary for {len(notes)} commits[/green]")

    except Exception as e:
        if not quiet:
            console.print(f"[yellow]⚠ Auto-summarization failed (non-blocking): {e}[/yellow]")


def _count_commits_since(last_sha: str, notes: list) -> int:
    """Count how many commits have occurred since the last summary"""
    try:
        # Find the index of the last summary commit
        last_index = next(i for i, n in enumerate(notes) if n.sha == last_sha)
        return len(notes) - last_index
    except StopIteration:
        return len(notes)


def _has_architectural_changes(notes: list) -> bool:
    """Check if commits contain architectural changes"""
    architectural_keywords = [
        "refactor",
        "architecture",
        "redesign",
        "migrate",
        "restructure",
        "component",
        "module",
        "interface",
        "contract",
        "protocol",
    ]

    return any(any(kw in (note.subject + " " + note.body).lower() for kw in architectural_keywords) for note in notes)


def _has_major_architectural_changes(notes: list) -> bool:
    """Check if commits contain major architectural changes"""
    major_keywords = [
        "major refactor",
        "complete redesign",
        "architecture overhaul",
        "migration to",
        "new framework",
        "rewrite",
        "rearchitecture",
    ]

    return any(any(kw in (note.subject + " " + note.body).lower() for kw in major_keywords) for note in notes)


def _generate_project_summary_from_commits(notes: list, namespace: str, user_id: str) -> dict:
    """Generate a project-level summary from recent commits"""
    from devmemory.commands.summarize import PROJECT_SUMMARY_PROMPT

    # Combine commit information
    context_parts = [f"Analyzing {len(notes)} recent commits:"]

    for i, note in enumerate(notes[:10]):  # Limit to 10 most recent
        context_parts.append(f"\n{i + 1}. {note.subject}")
        if note.body:
            context_parts.append(f"   {note.body[:200]}")

        # Add file changes
        files = [f.filepath for f in note.files[:5]]
        if files:
            context_parts.append(f"   Files: {', '.join(files)}")

        # Add AI usage info
        if note.has_ai_note:
            agents = set()
            for pd in note.prompts.values():
                if pd.tool:
                    agents.add(pd.tool)
            if agents:
                context_parts.append(f"   AI Agents: {', '.join(agents)}")

    context = "\n".join(context_parts)

    try:
        # Use the project summary prompt
        summary_text = generate_commit_summary.__wrapped__(
            notes[0],  # Use first commit as representative
            namespace=namespace,
            user_id=user_id,
            timeout=30.0,
        )

        if summary_text and "text" in summary_text:
            return {
                "id": f"project-summary-{notes[0].sha[:12]}",
                "text": f"Project Summary: {summary_text['text']}",
                "memory_type": "semantic",
                "topics": ["project-summary", "architecture", "evolution"],
                "entities": [namespace, "project"],
                "namespace": namespace,
                "user_id": user_id,
                "session_id": f"auto-summary-{notes[0].sha[:12]}",
            }
    except Exception:
        pass

    return None


def _generate_architecture_summary_from_commits(notes: list, namespace: str, user_id: str) -> dict:
    """Generate an architecture-level summary from recent commits"""
    from devmemory.commands.summarize import ARCHITECTURE_SUMMARY_PROMPT

    # Focus on architectural aspects
    arch_commits = [n for n in notes if _has_architectural_changes([n])]

    if not arch_commits:
        return None

    context_parts = [f"Analyzing {len(arch_commits)} architectural commits:"]

    for i, note in enumerate(arch_commits[:15]):  # More commits for architecture
        context_parts.append(f"\n{i + 1}. {note.subject}")
        if note.body:
            context_parts.append(f"   {note.body[:300]}")

        # Add file changes
        files = [f.filepath for f in note.files[:8]]
        if files:
            context_parts.append(f"   Files: {', '.join(files)}")

        # Add architectural details
        if note.has_ai_note and note.stats:
            stats = note.stats
            if stats.ai_additions > 50 or stats.human_additions > 100:
                context_parts.append(
                    f"   Significant changes: {stats.ai_additions} AI lines, {stats.human_additions} human lines"
                )

    context = "\n".join(context_parts)

    try:
        # Generate summary for the most significant architectural commit
        summary_text = generate_commit_summary.__wrapped__(
            arch_commits[0], namespace=namespace, user_id=user_id, timeout=30.0
        )

        if summary_text and "text" in summary_text:
            return {
                "id": f"architecture-summary-{notes[0].sha[:12]}",
                "text": f"Architecture Summary: {summary_text['text']}",
                "memory_type": "semantic",
                "topics": ["architecture-summary", "design", "patterns"],
                "entities": [namespace, "architecture"],
                "namespace": namespace,
                "user_id": user_id,
                "session_id": f"auto-summary-{notes[0].sha[:12]}",
            }
    except Exception:
        pass

    return None


def run_sync(
    latest: bool = False,
    all_commits: bool = False,
    ai_only: bool = True,
    dry_run: bool = False,
    limit: int = 50,
    quiet: bool = False,
    batch_size: int = 50,
    local_enrichment: bool = True,
    all_branches: bool = False,
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
        since_sha = None if (all_commits or all_branches) else (state.last_synced_sha or None)
        notes = get_ai_notes_since(since_sha, limit=limit, all_branches=all_branches)

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
    summary_memories = []

    ns = config.get_active_namespace()
    for n in notes_to_sync:
        if n.has_ai_note:
            memories = format_commit_as_memories(
                n, namespace=ns, user_id=config.user_id, local_enrichment=local_enrichment
            )
        else:
            memories = format_commit_without_ai(n, namespace=ns, user_id=config.user_id)

        if memories:
            all_memories.extend(memories)
            synced_shas.append(n.sha)

        if config.auto_summarize and n.has_ai_note:
            try:
                summary = generate_commit_summary(
                    n,
                    namespace=ns,
                    user_id=config.user_id,
                )
                if summary:
                    summary_memories.append(summary)
            except Exception:
                pass

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
                        console.print(f"  Sending batch {i // batch_size + 1} ({len(batch)} memories)...", end="\r")
                    client.create_memories(batch)
                    total_synced += len(batch)

            if not quiet:
                console.print(f"\n[green]✓ Successfully synced {total_synced} memories.[/green]")
        except Exception as e:
            if not quiet:
                console.print(f"\n[red]✗ Sync failed: {e}[/red]")
            raise typer.Exit(1)

    if summary_memories:
        try:
            with client:
                if not quiet:
                    console.print(f"[dim]Generating {len(summary_memories)} commit summary(ies)...[/dim]")
                client.create_memories(summary_memories)
                total_synced += len(summary_memories)
                if not quiet:
                    console.print(f"[green]✓ Generated {len(summary_memories)} commit summary(ies).[/green]")
        except Exception as e:
            if not quiet:
                console.print(f"[yellow]⚠ Summarization failed (non-blocking): {e}[/yellow]")

    # Auto-summarization for project and architecture levels
    if config.auto_summarize and len(notes_to_sync) >= 3:  # Only trigger for significant batches
        _trigger_auto_summarization(client=client, config=config, state=state, notes=notes_to_sync, quiet=quiet)

    if notes_to_sync:
        newest_sha = notes_to_sync[0].sha
        state.mark_synced(newest_sha, count=total_synced)

        if quiet:
            if total_synced > 0:
                print(f"devmemory: synced {total_synced} memory(s) from {len(notes_to_sync)} commit(s)")
        else:
            console.print(f"[dim]Last synced: {newest_sha[:12]}[/dim]")
