import typer
from rich.console import Console
from rich.table import Table
from dataclasses import asdict

from devmemory.core.config import DevMemoryConfig

app = typer.Typer()
console = Console()


@app.command("show")
def show():
    config = DevMemoryConfig.load()
    table = Table(title="DevMemory Configuration", show_header=True, border_style="dim")
    table.add_column("Key", style="bold")
    table.add_column("Value")

    for key, value in asdict(config).items():
        display = value if value else "[dim]not set[/dim]"
        table.add_row(key, str(display))

    console.print(table)


@app.command("set")
def set_value(
    key: str = typer.Argument(..., help="Config key to set."),
    value: str = typer.Argument(..., help="Value to set."),
):
    config = DevMemoryConfig.load()
    try:
        config.set_value(key, value)
        console.print(f"[green]Set {key} = {value}[/green]")
    except KeyError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)


@app.command("reset")
def reset():
    config = DevMemoryConfig()
    config.save()
    console.print("[green]Config reset to defaults.[/green]")
