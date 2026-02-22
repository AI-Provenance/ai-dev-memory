from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

import typer
from rich.console import Console

from devmemory.core.config import DevMemoryConfig
from devmemory.core.ams_client import AMSClient, MemoryResult

console = Console()

DEFAULT_OUTPUT = ".devmemory/CONTEXT.md"
RELEVANCE_THRESHOLD = 0.65
MAX_CONTEXT_CHARS = 4000
MAX_RESULTS_PER_QUERY = 5


def _git_cmd(args: list[str]) -> str:
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


def _build_search_queries(signals: dict) -> list[str]:
    queries = []

    branch = signals["branch"]
    if branch and branch not in ("main", "master", "HEAD", "unknown"):
        clean_branch = branch.replace("/", " ").replace("-", " ").replace("_", " ")
        queries.append(clean_branch)

    changed = signals["changed_files"]
    if changed:
        dirs = set()
        for f in changed[:10]:
            parts = f.rsplit("/", 1)
            if len(parts) == 2:
                dirs.add(parts[0].split("/")[-1])
        if dirs:
            queries.append(f"known issues and patterns in {' '.join(sorted(dirs)[:5])}")
        file_list = " ".join(changed[:5])
        queries.append(f"architecture decisions for {file_list}")

    subjects = signals["recent_subjects"]
    if subjects:
        combined = "; ".join(subjects[:3])
        queries.append(f"context for recent work: {combined}")

    if not queries:
        queries.append("project architecture and conventions")

    return queries[:5]


def _search_with_dedup(
    client: AMSClient,
    queries: list[str],
    namespace: str | None,
    threshold: float = RELEVANCE_THRESHOLD,
) -> list[MemoryResult]:
    seen_ids: set[str] = set()
    results: list[MemoryResult] = []

    for query in queries:
        try:
            hits = client.search_memories(
                text=query,
                limit=MAX_RESULTS_PER_QUERY,
                namespace=namespace,
                memory_type="semantic",
            )
        except Exception:
            continue

        for r in hits:
            if r.score < threshold and r.id not in seen_ids:
                seen_ids.add(r.id)
                results.append(r)

    results.sort(key=lambda r: r.score)
    return results


def _fetch_coordination_state(client: AMSClient) -> str | None:
    try:
        sessions = client.list_sessions(limit=10)
        for sid in sessions:
            if "coordination" in sid.lower():
                return sid
    except Exception:
        pass
    return None


def _truncate_memory_text(text: str, max_len: int = 200) -> str:
    lines = text.strip().splitlines()
    first_line = lines[0] if lines else ""
    if len(first_line) > max_len:
        return first_line[:max_len] + "..."
    if len(lines) == 1:
        return first_line

    result = first_line
    for line in lines[1:]:
        if len(result) + len(line) + 1 > max_len:
            break
        result += "\n" + line
    return result


def _render_context(
    signals: dict,
    results: list[MemoryResult],
    coordination_session: str | None,
) -> str:
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

    decisions = [
        r for r in results if any(t in r.topics for t in ("architecture", "decisions", "conventions", "dependencies"))
    ]
    gotchas = [r for r in results if any(t in r.topics for t in ("gotchas", "troubleshooting", "bugfix", "api-quirks"))]
    other = [r for r in results if r not in decisions and r not in gotchas]

    total_chars = sum(len(p) for p in parts)

    if decisions:
        parts.append("## Relevant Architecture Decisions\n")
        for r in decisions:
            summary = _truncate_memory_text(r.text)
            parts.append(f"- **{summary.splitlines()[0]}**")
            remaining = "\n".join(summary.splitlines()[1:]).strip()
            if remaining:
                for line in remaining.splitlines():
                    parts.append(f"  {line}")
            total_chars += len(summary)
            if total_chars > MAX_CONTEXT_CHARS:
                break
        parts.append("")

    if gotchas and total_chars < MAX_CONTEXT_CHARS:
        parts.append("## Known Gotchas for This Area\n")
        for r in gotchas:
            summary = _truncate_memory_text(r.text)
            parts.append(f"- **{summary.splitlines()[0]}**")
            remaining = "\n".join(summary.splitlines()[1:]).strip()
            if remaining:
                for line in remaining.splitlines():
                    parts.append(f"  {line}")
            total_chars += len(summary)
            if total_chars > MAX_CONTEXT_CHARS:
                break
        parts.append("")

    if other and total_chars < MAX_CONTEXT_CHARS:
        parts.append("## Other Relevant Context\n")
        for r in other:
            summary = _truncate_memory_text(r.text, max_len=150)
            first = summary.splitlines()[0]
            parts.append(f"- [{r.memory_type}] {first}")
            total_chars += len(first)
            if total_chars > MAX_CONTEXT_CHARS:
                break
        parts.append("")

    if coordination_session:
        parts.append("## Active Coordination\n")
        parts.append(f"- Active coordination session found: `{coordination_session}`")
        parts.append('- Use `get_working_memory(session_id="project-coordination")` via MCP to read details')
        parts.append("")

    if not results:
        parts.append("## No Relevant Memories Found\n")
        parts.append("No memories matched the current work area above the relevance threshold.")
        parts.append('Use `devmemory search "<query>"` for broader searches.')
        parts.append("")

    parts.append("---")
    parts.append(
        f"_Searched {len(results)} relevant memories across {len(signals.get('changed_files', []))} changed files._"
    )
    parts.append(
        '_For deeper context, use `devmemory search "<specific question>"` or `search_long_term_memory()` via MCP._'
    )

    return "\n".join(parts) + "\n"


def run_context(
    output: str = "",
    quiet: bool = False,
):
    config = DevMemoryConfig.load()
    client = AMSClient(base_url=config.ams_endpoint, auth_token=config.ams_auth_token)

    try:
        client.health_check()
    except Exception:
        if not quiet:
            console.print("[yellow]AMS not reachable — generating context from git signals only.[/yellow]")
        signals = _get_git_signals()
        content = _render_context(signals, [], None)
        _write_output(content, output, quiet)
        return

    if not quiet:
        console.print("[dim]Collecting git signals...[/dim]")

    signals = _get_git_signals()
    queries = _build_search_queries(signals)

    if not quiet:
        console.print(f"[dim]Searching memory with {len(queries)} queries...[/dim]")

    ns = config.get_active_namespace()
    results = _search_with_dedup(client, queries, ns)
    coordination = _fetch_coordination_state(client)
    content = _render_context(signals, results, coordination)
    _write_output(content, output, quiet)

    if not quiet:
        console.print(f"[green]Context generated with {len(results)} relevant memories.[/green]")


def _write_output(content: str, output: str, quiet: bool):
    out_path = Path(output) if output else Path.cwd() / DEFAULT_OUTPUT
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content)
    if not quiet:
        console.print(f"[dim]Written to {out_path}[/dim]")
