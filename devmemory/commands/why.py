from __future__ import annotations

import os
import subprocess

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from devmemory.core.config import DevMemoryConfig
from devmemory.core.llm_client import LLMError, call_llm, get_llm_config
import tiktoken

console = Console()

WHY_SYSTEM_PROMPT = """\
You are a code historian for a software project. You explain *why* code exists \
and how it evolved to its current state — like an intelligent git blame that \
tells the story behind the code.

Given a file path (and optionally a function/class name) along with retrieved \
memories from the project's memory store, provide a clear narrative that answers:

1. **Why this file exists**
2. **How it evolved (key events)**
3. **Who/what wrote it**

Rules:
- Output must contain EXACTLY these 3 sections, in this exact order, with these exact headings:
  - "Why this file exists"
  - "How it evolved (key events)"
  - "Who/what wrote it"
- Do not include any other headings or sections
- Each heading must be on its own line, followed by a blank line, then bullet points under it
- Keep it concise (aim for 8-15 bullet lines total across all sections)
- Reference specific commits (SHA) when relevant
- Mention the agent/model if the code was AI-generated
- If memories don't contain relevant information, say so clearly
- Focus on the "why" and "how", not just "what changed\""""

WHY_SYSTEM_PROMPT_VERBOSE = """\
You are a code historian for a software project. You explain *why* code exists \
and how it evolved to its current state — like an intelligent git blame that \
tells the story behind the code.

Given a file path (and optionally a function/class name) along with retrieved \
memories from the project's memory store, provide a clear narrative that answers:

1. **Why this file exists**
2. **How it evolved (key events)**
3. **Who/what wrote it**
4. **Key design decisions, trade-offs, and gotchas** (optional, only if supported by evidence)

Rules:
- Output must start with the 3 required sections using these exact headings, in this exact order:
  - "Why this file exists"
  - "How it evolved (key events)"
  - "Who/what wrote it"
- Each required heading must be on its own line, followed by a blank line, then bullet points under it
- You may add additional sections only after the 3 required sections, and only if supported by evidence
- Do not add a "Short answer" section
- Be concise but thorough — aim for a narrative, not a list of commits
- Reference specific commits (SHA) when relevant
- Mention the agent/model if the code was AI-generated
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


def _truncate_text(text: str, max_chars: int) -> str:
    """Truncate text to max_chars, preserving word boundaries."""
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    last_space = truncated.rfind(" ")
    if last_space > max_chars * 0.8:
        return truncated[:last_space] + "..."
    return truncated + "..."


def _estimate_tokens(text: str, model: str = "gpt-5-mini") -> int:
    try:
        if tiktoken is not None:
            try:
                enc = tiktoken.encoding_for_model(model)
            except KeyError:
                enc = tiktoken.get_encoding("o200k_base")
            return len(enc.encode(text))
    except Exception:
        return len(text) // 4
    return len(text) // 4


def _synthesize_why(
    filepath: str,
    function: str,
    memories: list[dict],
    git_context: str,
    verbose: bool = False,
    debug_mode: bool = False,
    model: str = "gpt-4o-mini",
) -> str | None:
    """Use LLM to synthesize a 'why' narrative from memories and git context."""
    MAX_INPUT_TOKENS = 8000
    MAX_OUTPUT_TOKENS = 2000

    system_prompt = WHY_SYSTEM_PROMPT_VERBOSE if verbose else WHY_SYSTEM_PROMPT
    system_prompt_tokens = _estimate_tokens(system_prompt, model=model)
    base_msg_tokens = _estimate_tokens(f"Explain why `{filepath}` exists and how it evolved.\n\n", model=model)

    available_tokens = MAX_INPUT_TOKENS - system_prompt_tokens - base_msg_tokens - MAX_OUTPUT_TOKENS

    git_context_truncated = _truncate_text(git_context, min(len(git_context), available_tokens // 2 * 4))
    git_tokens = _estimate_tokens(git_context_truncated, model=model)
    available_tokens -= git_tokens

    context_parts = []
    total_memory_chars = 0
    max_memory_chars = available_tokens * 4

    for i, mem in enumerate(memories, 1):
        topics_str = ", ".join(mem.get("topics", []))
        header = f"--- Memory {i} (type: {mem['type']}, score: {mem['score']:.3f}"
        if topics_str:
            header += f", topics: {topics_str}"
        header += ") ---"

        mem_text = mem.get("text", "")
        header_len = len(header) + 2

        remaining_chars = max_memory_chars - total_memory_chars - header_len
        if remaining_chars <= 100:
            break

        truncated_text = _truncate_text(mem_text, remaining_chars)
        context_parts.append(f"{header}\n{truncated_text}")
        total_memory_chars += len(header) + len(truncated_text) + 2

    memory_context = "\n\n".join(context_parts)

    truncated_count = len(memories) - len(context_parts)
    if truncated_count > 0:
        memory_context += f"\n\n[Note: {truncated_count} additional memories were truncated due to input length limits]"
        if verbose or debug_mode:
            console.print(f"[dim]Warning: Truncated {truncated_count} memories to fit within context window[/dim]")

    if len(git_context_truncated) < len(git_context):
        if verbose or debug_mode:
            console.print(
                f"[dim]Warning: Git history truncated ({len(git_context_truncated)}/{len(git_context)} chars)[/dim]"
            )

    target = f"`{filepath}`"
    if function:
        target += f" (specifically `{function}`)"

    user_msg = (
        f"Explain why {target} exists and how it evolved.\n\n"
        f"Git history for this file:\n{git_context_truncated}\n\n"
        f"Retrieved memories ({len(context_parts)} of {len(memories)} shown):\n\n{memory_context}"
    )

    return call_llm(system_prompt, user_msg, max_tokens=MAX_OUTPUT_TOKENS)


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
    verbose: bool = False,
):
    from devmemory.attribution.cloud_storage import CloudStorage

    config = DevMemoryConfig.load()

    # Check if API key is configured
    if not config.api_key:
        console.print("[yellow]⚠ This feature requires Cloud Edition[/yellow]")
        console.print("[dim]Get an API key at: https://aiprove.org[/dim]")
        console.print("")
        console.print("Local mode features available now:")
        console.print("  - devmemory attribution lookup <file>")
        console.print("  - devmemory sync")
        console.print("  - devmemory status")
        raise typer.Exit(0)

    # Use Cloud API
    client = CloudStorage(api_key=config.api_key)

    try:
        health = client.health_check()
        if health.get("status") != "ok":
            console.print(f"[red]Cloud API unhealthy: {health.get('message', 'Unknown error')}[/red]")
            raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Cannot reach Cloud API: {e}[/red]")
        console.print("[dim]Check your API key or try again later.[/dim]")
        raise typer.Exit(1)

    # Verify the file exists in the repo
    try:
        subprocess.run(
            ["git", "cat-file", "-e", f"HEAD:{filepath}"],
            capture_output=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        console.print(f"[red]File not found in repo: {filepath}[/red]")
        console.print("[dim]Provide a path relative to the repository root.[/dim]")
        raise typer.Exit(1)

    target_label = f"[cyan]{filepath}[/cyan]"
    if function:
        target_label += f" → [cyan]{function}[/cyan]"

    console.print(f"\n[dim]Investigating:[/dim] {target_label}")

    # Call Cloud API for explanation
    console.print("[dim]Querying cloud API...[/dim]")

    try:
        response = client.explain_why(filepath, function, limit, raw, verbose)

        if response.get("error"):
            console.print(f"[red]Why query failed: {response['error']}[/red]")
            raise typer.Exit(1)

        # Display results from API
        explanation = response.get("explanation", "No explanation available.")
        history = response.get("history", [])

        if raw:
            # Raw mode - show git history and API response
            git_log = _get_git_log_for_file(filepath, function)
            if git_log:
                console.print(Panel(git_log, title="[bold]Git History[/bold]", border_style="dim"))
            console.print(Panel(str(explanation), title="[bold]API Response[/bold]", border_style="dim"))
        else:
            # Normal mode - show synthesized explanation
            console.print("")
            console.print(Panel(Markdown(explanation), title="[bold]Explanation[/bold]", border_style="green"))

            if history:
                console.print("")
                console.print("[bold]History:[/bold]")
                for item in history:
                    console.print(f"  • {item}")

        console.print("")
        console.print(f"[dim]Quota remaining: {response.get('quota_remaining', 'N/A')}[/dim]")

    except Exception as e:
        console.print(f"[red]Why query failed: {e}[/red]")

        # Fallback to git history only
        git_log = _get_git_log_for_file(filepath, function)
        if git_log:
            console.print("")
            console.print("[dim]Showing git history only:[/dim]")
            console.print(Panel(git_log, title="[bold]Git History[/bold]", border_style="dim"))
            return  # Don't exit with error if we showed git history
        else:
            console.print("[yellow]No information available.[/yellow]")
            raise typer.Exit(1)
