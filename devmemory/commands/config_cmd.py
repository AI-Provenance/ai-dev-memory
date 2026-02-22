import typer
from rich.console import Console
from rich.table import Table
from dataclasses import asdict
import os

import json
from pathlib import Path
from devmemory.core.config import DevMemoryConfig, CONFIG_FILE
from devmemory.core.utils import get_repo_root

app = typer.Typer()
console = Console()


@app.command("show")
def show():
    # Load global only for comparison
    global_config = DevMemoryConfig()
    if CONFIG_FILE.exists():
        try:
            raw = json.loads(CONFIG_FILE.read_text())
            for k, v in raw.items():
                if k in global_config.__dataclass_fields__:
                    setattr(global_config, k, v)
        except Exception:
            pass

    config = DevMemoryConfig.load()
    repo_root = get_repo_root()
    local_data = {}
    if repo_root:
        local_file = Path(repo_root) / ".devmemory" / "config.json"
        if local_file.exists():
            try:
                local_data = json.loads(local_file.read_text())
            except Exception:
                pass

    table = Table(title="DevMemory Configuration", show_header=True, border_style="dim")
    table.add_column("Key", style="bold")
    table.add_column("Value")
    table.add_column("Source", style="dim")

    for key, value in asdict(config).items():
        display = str(value) if value else "[dim]not set[/dim]"
        source = "default"
        if key in local_data:
            source = "[cyan]local[/cyan]"
        elif CONFIG_FILE.exists():
            try:
                raw_global = json.loads(CONFIG_FILE.read_text())
                if key in raw_global:
                    source = "global"
            except Exception:
                pass
        table.add_row(key, display, source)

    # Add AMS_AUTH_TOKEN row (always from environment)
    auth_token = os.environ.get("AMS_AUTH_TOKEN", "")
    if auth_token:
        display = f"[dim]{auth_token[:4]}...{auth_token[-4:]}[/dim]" if len(auth_token) > 8 else "[dim]***[/dim]"
    else:
        display = "[dim]not set[/dim]"
    table.add_row("ams_auth_token", display, "[yellow]env[/yellow]")

    console.print(table)

    if repo_root:
        active_ns = config.get_active_namespace()
        console.print(f"\n[dim]Active scoped namespace:[/dim] [bold cyan]{active_ns}[/bold cyan]")
        console.print(f"[dim]Repository Root:[/dim] [dim]{repo_root}[/dim]")


@app.command("set")
def set_value(
    key: str = typer.Argument(..., help="Config key to set."),
    value: str = typer.Argument(..., help="Value to set."),
    local: bool = typer.Option(False, "--local", "-l", help="Save to local repository configuration."),
):
    config = DevMemoryConfig.load()

    # Prevent setting auth token from config - must use environment variable
    if key == "ams_auth_token":
        console.print(
            "[red]ams_auth_token cannot be set via config. Use AMS_AUTH_TOKEN environment variable instead.[/red]"
        )
        raise typer.Exit(1)

    try:
        field_type = config.__dataclass_fields__.get(key)
        parsed_value: str | bool = value
        if field_type and field_type.type == bool:  # type: ignore[union-attr]
            if value.lower() in ("true", "1", "yes", "on"):
                parsed_value = True
            elif value.lower() in ("false", "0", "no", "off"):
                parsed_value = False
            else:
                console.print(f"[red]Invalid boolean value: {value}. Use true/false, 1/0, yes/no, or on/off.[/red]")
                raise typer.Exit(1)
        config.set_value(key, parsed_value, local=local)  # type: ignore[arg-type]
        loc_str = " (local)" if local else " (global)"
        console.print(f"[green]Set {key} = {parsed_value}{loc_str}[/green]")
    except Exception as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)


@app.command("reset")
def reset():
    config = DevMemoryConfig()
    config.save()
    console.print("[green]Config reset to defaults.[/green]")
