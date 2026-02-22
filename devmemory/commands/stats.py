import json
from datetime import datetime, timezone, timedelta
from typing import Optional
import typer
from rich.console import Console
from rich.table import Table
from dataclasses import dataclass

from devmemory.core.config import DevMemoryConfig
from devmemory.core.ams_client import AMSClient
from devmemory.core.utils import get_repo_root
from devmemory.core.logging_config import get_logger

log = get_logger(__name__)
console = Console()

app = typer.Typer()

STATS_VIEW_NAME = "team-code-stats"
STATS_VIEW_ALL_TIME_NAME = "team-code-stats-all-time"
STATS_VIEW_PROMPT = """You are a code statistics analyzer. Given commit statistics, provide a concise summary of AI vs Human code contribution.

For each developer, report:
- Total lines added (Human vs AI)
- AI percentage
- Number of commits

Then provide overall team totals.

Format as:
### Per-Developer Stats
- email: X lines (Y% AI)

### Team Totals
- Total: X lines (Y% AI, Z% Human)
"""


@dataclass
class DeveloperStats:
    email: str
    human_additions: int = 0
    ai_additions: int = 0
    ai_accepted: int = 0
    commit_count: int = 0

    @property
    def total_lines(self) -> int:
        return self.human_additions + self.ai_additions

    @property
    def ai_percentage(self) -> float:
        if self.total_lines == 0:
            return 0.0
        return (self.ai_additions / self.total_lines) * 100

    @property
    def human_percentage(self) -> float:
        return 100.0 - self.ai_percentage


@dataclass
class TeamStats:
    developers: list[DeveloperStats]
    total_human: int = 0
    total_ai: int = 0

    @property
    def total_lines(self) -> int:
        return self.total_human + self.total_ai

    @property
    def ai_percentage(self) -> float:
        if self.total_lines == 0:
            return 0.0
        return (self.total_ai / self.total_lines) * 100

    @property
    def human_percentage(self) -> float:
        return 100.0 - self.ai_percentage


def parse_stats_from_memories(memories: list[dict], days: Optional[int] = None) -> TeamStats:
    """Parse commit stats from memory records."""
    cutoff_time = None
    if days:
        cutoff_time = datetime.now(timezone.utc) - timedelta(days=days)

    dev_stats: dict[str, DeveloperStats] = {}
    total_human = 0
    total_ai = 0

    for mem in memories:
        try:
            text = mem.get("text", "")
            stats_data = json.loads(text)

            commit_time_str = stats_data.get("timestamp", "")
            if commit_time_str and cutoff_time:
                try:
                    commit_time = datetime.fromisoformat(commit_time_str.replace("Z", "+00:00"))
                    if commit_time < cutoff_time:
                        continue
                except (ValueError, TypeError):
                    pass

            email = mem.get("user_id", "")
            if not email:
                continue

            if email not in dev_stats:
                dev_stats[email] = DeveloperStats(email=email)

            ds = dev_stats[email]
            ds.human_additions += stats_data.get("human_additions", 0)
            ds.ai_additions += stats_data.get("ai_additions", 0)
            ds.ai_accepted += stats_data.get("ai_accepted", 0)
            ds.commit_count += 1

            total_human += stats_data.get("human_additions", 0)
            total_ai += stats_data.get("ai_additions", 0)

        except (json.JSONDecodeError, KeyError, TypeError):
            continue

    return TeamStats(
        developers=list(dev_stats.values()),
        total_human=total_human,
        total_ai=total_ai,
    )


def format_bytes_size(num_bytes: int) -> str:
    """Format large numbers in a readable way."""
    if num_bytes >= 1000000:
        return f"{num_bytes / 1000000:.1f}M"
    elif num_bytes >= 1000:
        return f"{num_bytes / 1000:.1f}K"
    else:
        return str(num_bytes)


def ensure_stats_summary_view(client: AMSClient, namespace: str, time_window_days: int = 30, view_name: str = None):
    """Create or get the team stats summary view."""
    if view_name is None:
        view_name = STATS_VIEW_NAME
    try:
        views = client.list_summary_views()
        for view in views:
            if view.name == view_name:
                log.debug(f"stats view already exists: {view.id}")
                return view

        view_config = {
            "name": view_name,
            "source": "long_term",
            "group_by": ["user_id"],
            "filters": {
                "namespace": {"eq": namespace},
                "session_id": {"eq": "stats"},
            },
            "time_window_days": time_window_days,
            "prompt": STATS_VIEW_PROMPT,
            "continuous": True,
        }
        view = client.create_summary_view(view_config)
        console.print(f"[dim]Created summary view: {view.id}[/dim]")
        return view
    except Exception as e:
        log.warning(f"Failed to create summary view: {e}")
        return None


def get_or_create_stats_views(client: AMSClient, namespace: str, days: Optional[int] = None):
    """Ensure team stats summary views exist."""
    time_window = days or 30

    per_user_view = ensure_stats_summary_view(client, namespace, time_window, STATS_VIEW_NAME)
    all_time_view = ensure_stats_summary_view(
        client, namespace, time_window_days=365 * 10, view_name=STATS_VIEW_ALL_TIME_NAME
    )

    return per_user_view, all_time_view


@app.command()
def run_stats(
    team: bool = typer.Option(False, "--team", "-t", help="Show team-wide stats instead of individual"),
    days: Optional[int] = typer.Option(None, "--days", "-d", help="Filter to last N days (e.g., 30, 90)"),
    all_time: bool = typer.Option(False, "--all-time", help="Show all-time stats (no time filter)"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Minimal output"),
    create_views: bool = typer.Option(False, "--create-views", help="Create AMS summary views for team stats"),
    summarize: bool = typer.Option(False, "--summarize", "-s", help="Show LLM-generated summary from AMS views"),
):
    """Show code contribution stats (AI vs Human).

    By default shows individual stats. Use --team for team-wide stats.
    """
    config = DevMemoryConfig.load()

    if all_time:
        days = None
    elif days is None:
        days = 30

    repo_root = get_repo_root()
    if not repo_root:
        console.print("[red]Not in a git repository.[/red]")
        raise typer.Exit(1)

    client = AMSClient(base_url=config.ams_endpoint, auth_token=config.get_auth_token())

    try:
        client.health_check()
    except Exception as e:
        console.print(f"[red]Cannot reach AMS at {config.ams_endpoint}: {e}[/red]")
        raise typer.Exit(1)

    ns = config.get_active_namespace()
    current_user = config.user_id

    if not quiet:
        time_desc = f"Last {days} days" if days else "All time"
        if team:
            console.print(f"[bold]Team Code Stats[/bold] [dim]({time_desc})[/dim]\n")
        else:
            console.print(f"[bold]Your Code Stats[/bold] [dim]({time_desc})[/dim]\n")

    try:
        with client:
            log.info(f"stats: namespace={ns}, user_id={current_user}, team={team}")
            # Get all memories and filter for stats by ID prefix (more reliable than topic search)
            all_memories = client.search_memories(
                text="",
                namespace=ns,
                limit=100,
            )
            # Filter for stats memories by session_id
            memories = [m for m in all_memories if m.session_id == "stats"]
            if not team:
                # Filter by user_id
                memories = [m for m in memories if m.user_id == current_user]
            log.info(f"stats: found {len(memories)} stats memories")
    except Exception as e:
        console.print(f"[red]Failed to query stats: {e}[/red]")
        raise typer.Exit(1)

    if not memories:
        if team:
            console.print("[yellow]No team stats found. Run 'devmemory sync' first to collect stats.[/yellow]")
        else:
            console.print("[yellow]No stats found. Run 'devmemory sync' first to collect your stats.[/yellow]")
        raise typer.Exit(0)

    # Convert MemoryResult to dict format expected by parse_stats_from_memories
    # Need to preserve "text" key with the original JSON string, not parsed
    memories_data = []
    for m in memories:
        try:
            if not m.text:
                continue
            # Create dict with both text (for parse function) and user_id
            mem_dict = {"text": m.text, "user_id": m.user_id}
            memories_data.append(mem_dict)
        except Exception:
            continue

    team_stats = parse_stats_from_memories(memories_data, days=days)

    if not team_stats.developers:
        console.print("[yellow]No stats to display.[/yellow]")
        raise typer.Exit(0)

    if not quiet:
        table = Table(show_header=True, border_style="dim")
        table.add_column("Developer", style="bold")
        table.add_column("Commits", justify="right")
        table.add_column("Human", justify="right")
        table.add_column("AI", justify="right")
        table.add_column("AI %", justify="right")

        for dev in sorted(team_stats.developers, key=lambda d: d.ai_additions, reverse=True):
            human_str = format_bytes_size(dev.human_additions)
            ai_str = format_bytes_size(dev.ai_additions)
            ai_pct = f"{dev.ai_percentage:.0f}%"

            if dev.ai_percentage >= 50:
                ai_style = "cyan"
            elif dev.ai_percentage >= 25:
                ai_style = "yellow"
            else:
                ai_style = "green"

            table.add_row(
                dev.email,
                str(dev.commit_count),
                human_str,
                ai_str,
                f"[{ai_style}]{ai_pct}[/{ai_style}]",
            )

        console.print(table)
        console.print()

    total_lines = team_stats.total_lines
    if total_lines > 0:
        console.print(f"Total: {format_bytes_size(total_lines)} lines")
        console.print(
            f"  [green]{team_stats.human_percentage:.0f}%[/green] Human, "
            f"[cyan]{team_stats.ai_percentage:.0f}%[/cyan] AI"
        )
    else:
        console.print("[yellow]No lines to display.[/yellow]")

    try:
        with client:
            if create_views:
                per_user_view, all_time_view = get_or_create_stats_views(client, ns, days)
                if per_user_view and per_user_view.id:
                    console.print("\n[green]✓[/green] Created summary views:")
                    console.print(f"  [dim]Per-user stats: {per_user_view.id}[/dim]")
                    if all_time_view and all_time_view.id:
                        console.print(f"  [dim]All-time stats: {all_time_view.id}[/dim]")

            # Show LLM-generated summary from AMS views
            if summarize:
                from rich.panel import Panel

                views = client.list_summary_views()
                view_map = {v.name: v for v in views}

                view_name = STATS_VIEW_ALL_TIME_NAME if all_time else STATS_VIEW_NAME
                view = view_map.get(view_name)

                if not view:
                    console.print("[yellow]No summary view found. Run 'devmemory stats --create-views' first.[/yellow]")
                else:
                    partitions = client.get_summary_view_partitions(view.id, user_id=current_user if not team else None)

                    if partitions:
                        console.print(f"\n[bold]AI Summary (from AMS Summary View)[/bold]\n")
                        for p in partitions:
                            summary = p.get("summary", "No summary available")
                            group = p.get("group", {})
                            group_key = group.get("user_id", "team")
                            console.print(Panel(summary, title=f"[cyan]{group_key}[/cyan]", border_style="dim"))
                    else:
                        console.print(
                            "[yellow]No summary computed yet. The summary view may need time to process.[/yellow]"
                        )
                        console.print("[dim]Try running: devmemory stats --create-views[/dim]")
    except Exception as e:
        log.debug(f"Could not show summary: {e}")
