"""CLI for jadwal-sholat.

Usage examples:
    jadwal today --city jakarta
    jadwal next --city singapore
    jadwal today --lat -6.2 --lng 106.8 --tz Asia/Jakarta
    jadwal today --city london --method mwl --madhab hanafi
"""
from __future__ import annotations

import json
from datetime import date, datetime

import httpx
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from jadwal.core import CITY_COORDINATES, get_next_prayer, get_schedule

app = typer.Typer(
    help="Accurate prayer times in your terminal. Self-hostable, no API key required.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()


def _common_options(
    city: str | None,
    lat: float | None,
    lng: float | None,
    tz: str | None,
    method: str,
    madhab: str,
    target: date | None = None,
    refresh: bool = False,
):
    """Shared resolver — lets us surface user-friendly errors."""
    try:
        return get_schedule(
            city=city,
            lat=lat,
            lng=lng,
            timezone=tz,
            target_date=target,
            method=method,
            madhab=madhab,
            refresh=refresh,
        )
    except ValueError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(code=1) from e
    except httpx.HTTPError as e:
        console.print("[bold red]Error:[/bold red] Geocoding service unavailable. Try again later.")
        raise typer.Exit(code=1) from e


@app.command()
def today(
    city: str | None = typer.Option(
        None, "--city", "-c", help="City name (see `jadwal cities`) or any place name"
    ),
    lat: float | None = typer.Option(None, "--lat", help="Latitude (overrides --city)"),
    lng: float | None = typer.Option(None, "--lng", help="Longitude (overrides --city)"),
    tz: str | None = typer.Option(None, "--tz", help="Timezone (IANA, e.g. Asia/Jakarta)"),
    method: str = typer.Option("kemenag", "--method", "-m", help="Calculation method"),
    madhab: str = typer.Option("shafi", "--madhab", help="Shafi or Hanafi (affects Asr)"),
    json_out: bool = typer.Option(False, "--json", help="Output raw JSON"),
    refresh_cache: bool = typer.Option(
        False, "--refresh-cache", help="Force re-fetch coordinates from geocoder"
    ),
):
    """Show today's full prayer schedule."""
    schedule = _common_options(city, lat, lng, tz, method, madhab, refresh=refresh_cache)

    if json_out:
        console.print_json(json.dumps(schedule.to_dict()))
        return

    _render_schedule(schedule)


@app.command()
def now(
    city: str | None = typer.Option(None, "--city", "-c"),
    lat: float | None = typer.Option(None, "--lat"),
    lng: float | None = typer.Option(None, "--lng"),
    tz: str | None = typer.Option(None, "--tz"),
    method: str = typer.Option("kemenag", "--method", "-m"),
    madhab: str = typer.Option("shafi", "--madhab"),
    refresh_cache: bool = typer.Option(
        False, "--refresh-cache", help="Force re-fetch coordinates from geocoder"
    ),
):
    """Show the next upcoming prayer."""
    schedule = _common_options(city, lat, lng, tz, method, madhab, refresh=refresh_cache)
    nxt = get_next_prayer(schedule)

    body = Text()
    body.append(f"{nxt['name']}  ", style="bold cyan")
    body.append(f"at {nxt['time']}  ", style="white")
    body.append(f"({nxt['human']})", style="dim")

    console.print(Panel(body, title="Next Prayer", border_style="cyan"))


@app.command()
def on(
    day: str = typer.Argument(..., help="Date in YYYY-MM-DD format"),
    city: str | None = typer.Option(None, "--city", "-c"),
    lat: float | None = typer.Option(None, "--lat"),
    lng: float | None = typer.Option(None, "--lng"),
    tz: str | None = typer.Option(None, "--tz"),
    method: str = typer.Option("kemenag", "--method", "-m"),
    madhab: str = typer.Option("shafi", "--madhab"),
    json_out: bool = typer.Option(False, "--json"),
    refresh_cache: bool = typer.Option(
        False, "--refresh-cache", help="Force re-fetch coordinates from geocoder"
    ),
):
    """Show prayer times for a specific date."""
    try:
        target = datetime.strptime(day, "%Y-%m-%d").date()
    except ValueError as exc:
        console.print("[bold red]Error:[/bold red] Date must be in YYYY-MM-DD format.")
        raise typer.Exit(code=1) from exc

    schedule = _common_options(
        city, lat, lng, tz, method, madhab, target=target, refresh=refresh_cache
    )

    if json_out:
        console.print_json(json.dumps(schedule.to_dict()))
        return

    _render_schedule(schedule)


@app.command()
def cities():
    """List offline preset cities (any other name is resolved via the geocoder)."""
    table = Table(title="Built-in City Presets", border_style="dim")
    table.add_column("Name", style="cyan")
    table.add_column("Latitude", justify="right")
    table.add_column("Longitude", justify="right")
    table.add_column("Timezone")

    for name, (lat, lng, tz) in sorted(CITY_COORDINATES.items()):
        table.add_row(name, f"{lat:.4f}", f"{lng:.4f}", tz)

    console.print(table)
    console.print(
        "\n[dim]These are offline presets. Any other city name (e.g. 'Banda Aceh', "
        "'Toronto') will be resolved automatically via Open-Meteo geocoding.[/dim]"
    )


@app.command()
def lookup(
    name: str = typer.Argument(..., help="City or place name to look up"),
    refresh_cache: bool = typer.Option(
        False, "--refresh-cache", help="Force re-fetch from geocoder"
    ),
):
    """Look up coordinates and timezone for a city name via the geocoder."""
    from jadwal.geocoding import resolve_city

    try:
        result = resolve_city(name, refresh=refresh_cache)
    except ValueError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(code=1) from e
    except httpx.HTTPError as e:
        console.print("[bold red]Error:[/bold red] Geocoding service unavailable. Try again later.")
        raise typer.Exit(code=1) from e

    console.print(f"[bold cyan]{result.label}[/bold cyan]")
    console.print(f"  Latitude:  {result.lat}")
    console.print(f"  Longitude: {result.lng}")
    console.print(f"  Timezone:  {result.tz}")
    console.print(f"  [dim]Source: {result.source}[/dim]")


def _render_schedule(schedule):
    """Pretty-print a schedule as a table."""
    table = Table(
        title=f"Prayer Times  •  {schedule.location}  •  {schedule.date}",
        border_style="dim",
        title_style="bold cyan",
    )
    table.add_column("Prayer", style="cyan", no_wrap=True)
    table.add_column("Time", style="white", justify="right")

    for name, time in schedule.as_list():
        style = "dim italic" if name == "Sunrise" else ""
        table.add_row(name, time, style=style)

    console.print(table)
    console.print(
        f"[dim]Method: {schedule.method}  •  Timezone: {schedule.timezone}[/dim]"
    )
    console.print(
        "\n[dim]* Note: Times may vary slightly (±1 min) from official sources\n"
        "  or other apps due to differences in rounding logic and elevation.[/dim]"
    )


if __name__ == "__main__":
    app()
