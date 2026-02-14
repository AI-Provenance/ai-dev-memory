from __future__ import annotations

import subprocess

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from devmemory.core.config import DevMemoryConfig
from devmemory.core.ams_client import AMSClient, MemoryResult

console = Console()

WHY_SYSTEM_PROMPT = """\
You are a code historian for a software project. You explain *why* code exists \
and how it evolved to its current state — like an intelligent git blame that \
tells the story behind the code.

Given a file path (and optionally a function/class name) along with retrieved \
memories from the project's memory store, provide a clear narrative that answers:

1. **Why does this code exist?** — What problem or feature drove its creation?
2. **How did it evolve?** — Key changes, refactors, or fixes over time.
3. **Who/what wrote it?** — Was it human-authored or AI-generated? Which agent/model?
4. **Key decisions** — Any notable design choices, trade-offs, or gotchas.

Rules:
- Be concise but thorough — aim for a narrative, not a list of commits
- Reference specific commits (SHA) when relevant
- Mention the agent/model if the code was AI-generated
- If you see a pattern of changes (e.g., multiple bug fixes), explain the root cause
- If memories don't contain relevant information, say so clearly
- Focus on the "why" and "how", not just "what changed\""""

DEFAULT_THRESHOLD = 0.80


def _get_git_log_for_file(filepath: str, function: str = "", limit: int = 20) -> str:
    """Get recent git log entries for a file, optionally filtered to a function."""
    cmd = ["git", "log", f"-{limit}", "--format=%H|%an|%s|%aI", "--follow", "--", filepath]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""

    return result.stdout.strip()


def _get_git_blame_summary(filepath: str, function: str = "") -> str:
    """Get a concise blame summary showing who last touched each section."""
    if function:
        # Try to get line range for function using git log -L
        cmd = ["git", "log", "-1", f"-L:/{function}/:{filepath}", "--format=%H %an: %s"]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            if result.stdout.strip():
                return result.stdout.strip()[:2000]
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

    # Fallback: porcelain blame summary
    cmd = ["git", "blame", "--porcelain", filepath]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""

    # Extract unique author+commit pairs
    authors: dict[str, set[str]] = {}
    current_sha = ""
    current_author = ""
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 3 and len(parts[0]) == 40:
            current_sha = parts[0][:12]
        elif line.startswith("author "):
            current_author = line[7:].strip()
        elif line.startswith("summary "):
            summary = line[8:].strip()
            key = current_author or "unknown"
            if key not in authors:
                authors[key] = set()
            authors[key].add(f"{current_sha}: {summary}")

    lines = []
    for author, commits in authors.items():
        lines.append(f"{author}: {len(commits)} commit(s)")
        for c in list(commits)[:3]:
            lines.append(f"  - {c}")
    return "\n".join(lines)[:2000]


def _build_query(filepath: str, function: str = "") -> str:
    """Build a search query for the memory store."""
    if function:
        return f"{filepath} {function} implementation history decisions"
    return f"{filepath} implementation history decisions changes"


def _synthesize_why(
    filepath: str,
    function: str,
    memories: list[dict],
    git_context: str,
) -> str | None:
    """Use LLM to synthesize a 'why' narrative from memories and git context."""
    from devmemory.core.llm_client import call_llm

    # Build memory context
    context_parts = []
    for i, mem in enumerate(memories, 1):
        topics_str = ", ".join(mem.get("topics", []))
        header = f"--- Memory {i} (type: {mem['type']}, score: {mem['score']:.3f}"
        if topics_str:
            header += f", topics: {topics_str}"
        header += ") ---"
        context_parts.append(f"{header}\n{mem['text']}")

    memory_context = "\n\n".join(context_parts)

    target = f"`{filepath}`"
    if function:
        target += f" (specifically `{function}`)"

    user_msg = (
        f"Explain why {target} exists and how it evolved.\n\n"
        f"Git history for this file:\n{git_context}\n\n"
        f"Retrieved memories ({len(memories)} results):\n\n{memory_context}"
    )

    return call_llm(WHY_SYSTEM_PROMPT, user_msg, max_tokens=1500)


def _display_sources(results: list[MemoryResult]):
    if not results:
        return

    table = Table(show_header=True, header_style="bold dim", box=None, padding=(0, 1))
    table.add_column("#", style="bold", width=3)
    table.add_column("Score", width=7)
    table.add_column("Type", style="dim", width=10)
    table.add_column("Topics", no_wrap=False)

    for i, r in enumerate(results, 1):
        score_color = "green" if r.score < 0.4 else "yellow" if r.score < 0.65 else "red"
        score_text = Text(f"{r.score:.3f}", style=score_color)
        type_text = Text(r.memory_type, style="cyan" if r.memory_type == "semantic" else "dim")
        topics = ", ".join(r.topics[:5]) if r.topics else ""
        table.add_row(str(i), score_text, type_text, topics)

    console.print(f"\n[bold]Sources[/bold] ({len(results)} memories used)\n")
    console.print(table)


def run_why(
    filepath: str,
    function: str = "",
    limit: int = 15,
    raw: bool = False,
):
    config = DevMemoryConfig.load()
    client = AMSClient(base_url=config.ams_endpoint)

    try:
        client.health_check()
    except Exception as e:
        console.print(f"[red]Cannot reach AMS at {config.ams_endpoint}: {e}[/red]")
        raise typer.Exit(1)

    # Verify the file exists in the repo
    try:
        subprocess.run(
            ["git", "cat-file", "-e", f"HEAD:{filepath}"],
            capture_output=True, check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        console.print(f"[red]File not found in repo: {filepath}[/red]")
        console.print("[dim]Provide a path relative to the repository root.[/dim]")
        raise typer.Exit(1)

    target_label = f"[cyan]{filepath}[/cyan]"
    if function:
        target_label += f" → [cyan]{function}[/cyan]"

    console.print(f"\n[dim]Investigating:[/dim] {target_label}")

    # Gather git context
    git_log = _get_git_log_for_file(filepath, function)
    blame_summary = _get_git_blame_summary(filepath, function)

    git_context = ""
    if git_log:
        git_context += f"Recent commits:\n{git_log}\n\n"
    if blame_summary:
        git_context += f"Blame summary:\n{blame_summary}"

    if not git_context.strip():
        console.print("[yellow]No git history found for this file.[/yellow]")

    # Search memory store
    query = _build_query(filepath, function)
    ns = config.namespace or None

    console.print("[dim]Searching memories...[/dim]")

    results: list[MemoryResult] = []
    try:
        results = client.search_memories(
            text=query,
            limit=limit * 3,
            namespace=ns,
        )
    except Exception as e:
        console.print(f"[yellow]Memory search failed: {e}[/yellow]")
        console.print("[dim]Continuing with git history only...[/dim]")

    # Also search with just the filename for broader matches
    filename_only = filepath.rsplit("/", 1)[-1] if "/" in filepath else filepath
    if results and filename_only != filepath:
        try:
            extra = client.search_memories(
                text=f"{filename_only} why changes",
                limit=limit,
                namespace=ns,
            )
            seen_ids = {r.id for r in results}
            for r in extra:
                if r.id not in seen_ids:
                    results.append(r)
                    seen_ids.add(r.id)
        except Exception:
            pass

    # Filter and sort
    relevant = [r for r in results if r.score < DEFAULT_THRESHOLD]
    if not relevant and results:
        relevant = results[:limit]

    relevant.sort(key=lambda r: r.score)
    relevant = relevant[:limit]

    if raw:
        if not relevant and not git_context.strip():
            console.print("[yellow]No information found for this file.[/yellow]")
            raise typer.Exit(0)

        if git_context.strip():
            console.print(Panel(git_context.strip(), title="[bold]Git History[/bold]", border_style="dim"))

        for i, r in enumerate(relevant, 1):
            score_color = "green" if r.score < 0.4 else "yellow" if r.score < 0.65 else "red"
            header = Text()
            header.append(f"#{i} ", style="bold")
            header.append(f"[{r.score:.3f}] ", style=score_color)
            if r.topics:
                header.append(f"({', '.join(r.topics[:5])}) ", style="dim cyan")
            header.append(f"[{r.memory_type}]", style="dim")
            console.print(Panel(r.text, title=header, border_style="dim", padding=(0, 1)))
        return

    # Synthesize answer
    if not relevant and not git_context.strip():
        console.print("[yellow]No memories or git history found for this file.[/yellow]")
        console.print("[dim]The file may not have been synced yet. Try: devmemory sync --all[/dim]")
        raise typer.Exit(0)

    memories_for_llm = [
        {
            "text": r.text,
            "type": r.memory_type,
            "score": r.score,
            "topics": r.topics,
        }
        for r in relevant
    ]

    console.print("[dim]Synthesizing explanation...[/dim]\n")

    try:
        from devmemory.core.llm_client import LLMError
        answer = _synthesize_why(filepath, function, memories_for_llm, git_context)
    except Exception as e:
        error_str = str(e)
        if "no_api_key" in error_str:
            console.print("[yellow]No API key found for answer synthesis.[/yellow]")
            console.print("[dim]Set OPENAI_API_KEY in .env or environment. Falling back to raw output...[/dim]\n")
        else:
            console.print(f"[yellow]Synthesis failed: {error_str}[/yellow]")
            console.print("[dim]Falling back to raw output...[/dim]\n")
        run_why(filepath=filepath, function=function, limit=limit, raw=True)
        return

    if answer:
        title = f"[bold green]Why {filepath}"
        if function:
            title += f" → {function}"
        title += "[/bold green]"

        console.print(Panel(
            Markdown(answer),
            title=title,
            border_style="green",
            padding=(1, 2),
        ))

    _display_sources(relevant)
