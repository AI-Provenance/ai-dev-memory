from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from devmemory.core.config import DevMemoryConfig
from devmemory.core.ams_client import AMSClient, MemoryResult

console = Console()


def _sort_by_created(results: list[MemoryResult]) -> list[MemoryResult]:
    def key(r: MemoryResult) -> tuple:
        created = (r.created_at or "").strip()
        return (0 if created else 1, created)

    return sorted(results, key=key, reverse=True)


def run_prompts(
    limit: int = 50,
    namespace: str = "",
    all_repos: bool = False,
) -> None:
    config = DevMemoryConfig.load()
    if all_repos:
        ns = namespace or None
    else:
        ns = namespace or config.get_active_namespace()
    base_url = config.ams_endpoint or "http://localhost:8000"
    client = AMSClient(base_url=base_url, auth_token=config.get_auth_token())

    try:
        client.health_check()
    except Exception as e:
        console.print(f"[red]AMS unreachable at {base_url}: {e}[/red]")
        raise typer.Exit(1)

    results = client.search_memories(
        text="",
        limit=min(limit, 200),
        namespace=ns,
        topics=["prompt"],
    )
    if not results:
        results = client.search_memories(
            text="Stored AI prompt",
            limit=min(limit * 2, 200),
            namespace=ns,
            topics=["prompt"],
        )
    real_prompt_prefix = "Stored AI prompt for this repository."
    real_prompts = [r for r in results if (r.text or "").strip().startswith(real_prompt_prefix)]
    other_prompt_mentions = [
        r
        for r in results
        if r not in real_prompts and ("Stored AI prompt" in (r.text or "") or "Prompt to" in (r.text or ""))
    ]
    results = _sort_by_created(real_prompts)[:limit]

    if not results:
        console.print("[yellow]No stored user/assistant prompt memories in AMS.[/yellow]")
        if other_prompt_mentions:
            console.print(
                f"[dim]Found {len(other_prompt_mentions)} other memory(ies) that mention 'prompt' (code/commits), but none are the actual prompts from git-ai.[/dim]"
            )
        console.print("[dim]Ensure: git-ai config set prompt_storage notes, then devmemory sync --all[/dim]")
        raise typer.Exit(0)

    def _excerpt(text: str, max_len: int = 200) -> str:
        t = (text or "").strip()
        for marker in ("Stored AI prompt", "Prompt to"):
            if marker in t:
                start = t.find(marker)
                chunk = t[start:].replace("\n", " ").strip()
                if len(chunk) > max_len:
                    chunk = chunk[:max_len] + "..."
                return chunk
        one = t.replace("\n", " ").strip()
        return one[:max_len] + ("..." if len(one) > max_len else "")

    table = Table(title=f"Prompt memories (newest first, namespace={ns or 'default'})")
    table.add_column("created_at", style="dim", width=28)
    table.add_column("id", style="cyan", width=14)
    table.add_column("text (excerpt)", style="white", max_width=70, overflow="fold")

    for r in results:
        created = (r.created_at or "")[:28]
        excerpt = _excerpt(r.text)
        table.add_row(created, (r.id or "")[:14], excerpt)

    console.print(table)
    console.print(f"[dim]{len(results)} prompt memory(ies) shown.[/dim]")
