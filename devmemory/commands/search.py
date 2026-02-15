import re

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from rich.table import Table

from devmemory.core.config import DevMemoryConfig
from devmemory.core.ams_client import AMSClient, MemoryResult

console = Console()

DEFAULT_THRESHOLD = 0.75

RECENCY_WORDS = ("recent", "latest", "last", "newest")


def _query_wants_recency(query: str) -> bool:
    q = query.lower()
    return any(w in q for w in RECENCY_WORDS)


def _sort_by_recency(results: list[MemoryResult]) -> list[MemoryResult]:
    def key(r: MemoryResult) -> tuple:
        created = (r.created_at or "").strip()
        return (0 if created else 1, created)

    return sorted(results, key=key, reverse=True)


def _extract_source_label(result: MemoryResult) -> str:
    text = result.text
    lines = text.strip().splitlines()
    if not lines:
        return "unknown"

    first_line = lines[0].strip()

    if result.memory_type == "episodic":
        file_match = re.match(r"File:\s*(.+)", first_line)
        if file_match:
            filepath = file_match.group(1).strip()
            commit_line = next((l for l in lines if l.startswith("Commit:")), "")
            sha_match = re.search(r"\(([a-f0-9]{12})\)", commit_line)
            sha = sha_match.group(1) if sha_match else ""
            label = filepath
            if sha:
                label += f" ({sha})"
            return label

        commit_match = re.match(r"Commit\s*\(human-authored\):\s*(.+)", first_line)
        if commit_match:
            return commit_match.group(1).strip()[:60]

    if result.memory_type == "semantic":
        prompt_match = re.match(r"Prompt to (.+?):", first_line)
        if prompt_match:
            agent = prompt_match.group(1).strip()
            user_msg = ""
            for line in lines[1:]:
                if line.strip().startswith("[user]:"):
                    user_msg = line.strip()[7:].strip()[:80]
                    break
            label = f"Prompt → {agent}"
            if user_msg:
                label += f': "{user_msg}"'
            return label

        merged = first_line.strip("*").strip().lower().startswith("merged memory")
        if merged:
            commit_line = ""
            sha = ""
            for line in lines:
                clean = line.strip().strip("*").strip()
                if clean.lower().startswith("commit message:") or clean.lower().startswith("- **commit message:**"):
                    commit_line = re.sub(r"^.*?commit message:\**\s*", "", clean, flags=re.IGNORECASE).strip()
                elif clean.startswith("SHA:") or clean.startswith("- **SHA:**"):
                    sha = re.sub(r"^.*?SHA:\**\s*", "", clean, flags=re.IGNORECASE).strip()[:12]
            label = commit_line[:60] if commit_line else "Merged memory"
            if sha:
                label += f" ({sha})"
            return label

        commit_match = re.match(r"Commit:\s*(.+)", first_line)
        if commit_match:
            subject = commit_match.group(1).strip()[:60]
            sha_line = next((l for l in lines if l.startswith("SHA:")), "")
            sha = sha_line.replace("SHA:", "").strip()[:12] if sha_line else ""
            if sha:
                return f"{subject} ({sha})"
            return subject

    return first_line[:60]


def _display_sources(results: list[MemoryResult], total_fetched: int, threshold: float):
    filtered_count = total_fetched - len(results)

    header = f"[bold]Sources[/bold] ({len(results)} relevant"
    if filtered_count > 0:
        header += f", {filtered_count} filtered out"
    header += ")"
    console.print(f"\n{header}\n")

    table = Table(show_header=True, header_style="bold dim", box=None, padding=(0, 1))
    table.add_column("#", style="bold", width=3)
    table.add_column("Score", width=7)
    table.add_column("Type", style="dim", width=10)
    table.add_column("Source", no_wrap=False)

    for i, r in enumerate(results, 1):
        score_color = "green" if r.score < 0.4 else "yellow" if r.score < 0.65 else "red"
        score_text = Text(f"{r.score:.3f}", style=score_color)
        type_text = Text(r.memory_type, style="cyan" if r.memory_type == "semantic" else "dim")
        label = _extract_source_label(r)
        table.add_row(str(i), score_text, type_text, label)

    console.print(table)


def _display_answer_mode(
    query: str,
    results: list[MemoryResult],
    total_fetched: int,
    threshold: float,
):
    from devmemory.core.llm_client import synthesize_answer, LLMError

    if not results:
        console.print("[yellow]No memories found matching your query.[/yellow]")
        return

    memories_for_llm = [
        {
            "text": r.text,
            "type": r.memory_type,
            "score": r.score,
            "topics": r.topics,
        }
        for r in results
    ]

    console.print(f"\n[dim]Searching for:[/dim] [cyan]{query}[/cyan]")
    console.print("[dim]Synthesizing answer...[/dim]\n")

    try:
        answer = synthesize_answer(query, memories_for_llm)
    except LLMError as e:
        error_str = str(e)
        if "no_api_key" in error_str:
            console.print("[yellow]No API key found for answer synthesis.[/yellow]")
            console.print("[dim]Set OPENAI_API_KEY environment variable or add it to .env file.[/dim]")
        else:
            console.print(f"[yellow]Answer synthesis failed: {error_str}[/yellow]")
        console.print("[dim]Falling back to raw results...[/dim]\n")
        _display_raw_results(query, results)
        return
    except Exception as e:
        console.print(f"[yellow]Answer synthesis failed: {e}[/yellow]")
        console.print("[dim]Falling back to raw results...[/dim]\n")
        _display_raw_results(query, results)
        return

    if answer and answer.strip():
        console.print(Panel(
            Markdown(answer),
            title="[bold green]Answer[/bold green]",
            border_style="green",
            padding=(1, 2),
        ))
    else:
        prompt_sources = [r for r in results if "prompt" in r.topics or "Prompt to" in r.text or "Stored AI prompt" in r.text]
        if prompt_sources and "prompt" in query.lower():
            excerpt = prompt_sources[0].text
            if len(excerpt) > 800:
                excerpt = excerpt[:797] + "..."
            console.print(Panel(
                excerpt,
                title="[bold green]Answer[/bold green] (excerpt from top prompt memory)",
                border_style="green",
                padding=(1, 2),
            ))
        else:
            console.print(Panel(
                "No synthesized answer. See sources below for retrieved memories.",
                title="[bold green]Answer[/bold green]",
                border_style="dim",
                padding=(1, 2),
            ))

    _display_sources(results, total_fetched, threshold)


def _display_raw_results(query: str, results: list[MemoryResult]):
    console.print(f"\n[bold]Found {len(results)} result(s) for:[/bold] [cyan]{query}[/cyan]\n")

    for i, r in enumerate(results, 1):
        score_color = "green" if r.score < 0.4 else "yellow" if r.score < 0.65 else "red"
        header = Text()
        header.append(f"#{i} ", style="bold")
        header.append(f"[{r.score:.3f}] ", style=score_color)
        if r.topics:
            header.append(f"({', '.join(r.topics[:5])}) ", style="dim cyan")
        header.append(f"[{r.memory_type}]", style="dim")

        console.print(Panel(
            r.text,
            title=header,
            border_style="dim",
            padding=(0, 1),
        ))


def run_search(
    query: str,
    limit: int = 10,
    namespace: str = "",
    topic: list[str] | None = None,
    memory_type: str = "",
    threshold: float = DEFAULT_THRESHOLD,
    raw: bool = False,
):
    config = DevMemoryConfig.load()
    client = AMSClient(base_url=config.ams_endpoint)

    try:
        client.health_check()
    except Exception as e:
        console.print(f"[red]Cannot reach AMS at {config.ams_endpoint}: {e}[/red]")
        raise typer.Exit(1)

    ns = namespace or config.namespace or None
    topics = topic if topic else None
    mtype = memory_type or None

    fetch_limit = limit * 3 if not raw else limit
    if topics == ["prompt"]:
        fetch_limit = max(fetch_limit, 80)

    try:
        results = client.search_memories(
            text=query,
            limit=fetch_limit,
            namespace=ns,
            topics=topics,
            memory_type=mtype,
        )
    except Exception as e:
        console.print(f"[red]Search failed: {e}[/red]")
        raise typer.Exit(1)

    if topics:
        results = [r for r in results if r.topics and any(t in r.topics for t in topics)]
    if topics == ["prompt"]:
        results = [
            r for r in results
            if "Stored AI prompt" in r.text or "Prompt to" in r.text
        ]

    if _query_wants_recency(query) and results:
        results = _sort_by_recency(results)

    if raw:
        if not results:
            console.print("[yellow]No memories found matching your query.[/yellow]")
            raise typer.Exit(0)
        _display_raw_results(query, results)
        return

    total_fetched = len(results)

    relevant = [r for r in results if r.score < threshold]

    if not relevant and results:
        console.print(
            f"[yellow]No memories passed relevance threshold ({threshold}).[/yellow]"
        )
        console.print(
            f"[dim]Best match score: {results[0].score:.3f} "
            f"(lower is better, threshold: {threshold})[/dim]"
        )
        console.print("[dim]Trying with top results anyway...[/dim]\n")
        relevant = results[:limit]

    semantic_results = [r for r in relevant if r.memory_type == "semantic"]
    episodic_results = [r for r in relevant if r.memory_type == "episodic"]
    prioritized = semantic_results + episodic_results
    prioritized = prioritized[:limit]

    _display_answer_mode(query, prioritized, total_fetched, threshold)
