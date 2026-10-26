"""Reusable Rich UI rendering components: header, panels, tables, and error displays."""

from typing import Any

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from voxclone.constants import APP_NAME
from voxclone.errors import VoxcloneError
from voxclone.ui.theme import Theme, badge


def make_console(theme: Theme, plain: bool = False) -> Console:
    """Instantiate a Rich Console adhering to width limits and display mode."""
    width = 100
    try:
        import shutil

        term_width = shutil.get_terminal_size((100, 24)).columns
        width = min(term_width, 100)
    except Exception:
        pass

    if plain:
        return Console(
            width=width,
            no_color=True,
            highlight=False,
            markup=False,
            force_terminal=False,
        )

    return Console(
        width=width,
        no_color=theme.no_color,
        highlight=not theme.plain,
        color_system=None if theme.no_color else "auto",
    )


def render_header(console: Console, state: Any) -> None:
    """Render the standard application top status header."""
    from voxclone import __version__

    profile_name = state.selected_profile_name or "(none)"

    # Device & Model info
    device_name = "auto"
    model_name = "none"
    vram_text = "n/a"

    if hasattr(state, "model_manager") and state.model_manager is not None:
        try:
            status = state.model_manager.status()
            model_name = status.resident_key or "none"
            device_name = status.device
            if status.vram_free_mb is not None:
                vram_text = f"{round(status.vram_free_mb / 1024, 1)} GB free"
        except Exception:
            pass
    elif hasattr(state, "config") and state.config:
        device_name = state.config.env_overrides.get("device", state.config.device)

    if getattr(state, "plain", False):
        console.print(f"=== {APP_NAME} v{__version__} ===")
        console.print(
            f"profile: {profile_name} | device: {device_name} | model: {model_name} | VRAM: {vram_text}"
        )
        console.print("-" * 50)
        return

    content = (
        f"[bold cyan]{APP_NAME}[/bold cyan] [dim]v{__version__}[/dim]\n"
        f"[dim]profile:[/dim] [bold]{profile_name}[/bold]   "
        f"[dim]device:[/dim] [bold]{device_name}[/bold]   "
        f"[dim]model:[/dim] [bold]{model_name}[/bold]   "
        f"[dim]VRAM:[/dim] {vram_text}"
    )

    console.print(
        Panel(
            content,
            box=box.ROUNDED,
            border_style="cyan",
            expand=False,
        )
    )


def render_model_loading_banner(
    console: Console,
    model_key: str,
    estimated_mb: int,
    plain: bool = False,
) -> None:
    """Render a transient banner when an AI neural model is loading into VRAM."""
    msg = f"Loading model '{model_key}' into memory (~{estimated_mb} MB VRAM)..."
    if plain:
        console.print(f"[MODEL LOAD] {msg}")
    else:
        console.print(f"[bold yellow]⏳ {msg}[/bold yellow]")



def render_panel(
    console: Console,
    title: str,
    lines: list[str],
    kind: str = "info",
    plain: bool = False,
) -> None:
    """Render a text block inside a styled Rich panel or plain lines."""
    if plain:
        console.print(f"[{title}]")
        for line in lines:
            console.print(f"  {line}")
        return

    border_color = "cyan"
    if kind == "success":
        border_color = "green"
    elif kind == "warning":
        border_color = "yellow"
    elif kind == "error":
        border_color = "red"

    body = "\n".join(lines)
    console.print(
        Panel(
            body,
            title=f"[bold]{title}[/bold]",
            border_style=border_color,
            box=box.ROUNDED,
            expand=False,
        )
    )


def render_table(
    console: Console,
    title: str,
    columns: list[str],
    rows: list[list[str]],
    plain: bool = False,
) -> None:
    """Render structured tabular data using Rich Table or ASCII lines."""
    if plain:
        console.print(f"=== {title} ===")
        header_line = " | ".join(columns)
        console.print(header_line)
        console.print("-" * len(header_line))
        for row in rows:
            console.print(" | ".join(str(cell) for cell in row))
        console.print("")
        return

    table = Table(
        title=title,
        box=box.ROUNDED,
        header_style="bold cyan",
        title_style="bold white",
    )
    for col in columns:
        table.add_column(col)

    for row in rows:
        table.add_row(*[str(cell) for cell in row])

    console.print(table)


def render_error(
    console: Console,
    err: VoxcloneError,
    debug: bool = False,
    theme: Theme | None = None,
) -> None:
    """Render standardized error message and action hint."""
    from voxclone.ui.theme import ASCII_ICONS, get_theme

    effective_theme = theme if theme is not None else get_theme(plain=console.no_color, no_color=console.no_color)
    err_icon, _, err_style = badge("error", theme=effective_theme)

    if console.no_color or effective_theme.plain:
        err_icon = ASCII_ICONS.get("error", "[X]")
        console.print(f"{err_icon} {err.message} ({err.code})")
        if err.hint:
            console.print(f"  -> {err.hint}")
    else:
        try:
            console.print(f"[{err_style}]{err_icon} {err.message} ({err.code})[/{err_style}]")
        except UnicodeEncodeError:
            err_icon = ASCII_ICONS.get("error", "[X]")
            console.print(f"{err_icon} {err.message} ({err.code})")
        if err.hint:
            console.print(f"  [dim cyan]-> {err.hint}[/dim cyan]")

    if debug and err.__cause__ is not None:
        import traceback

        tb = "".join(traceback.format_exception(type(err.__cause__), err.__cause__, err.__cause__.__traceback__))
        console.print(Panel(tb, title="Debug Exception Traceback", border_style="red"))


def render_status_line(
    console: Console,
    state_name: str,
    text: str,
    theme: Theme | None = None,
) -> None:
    """Render single-line status item with icon badge."""
    icon, word, style = badge(state_name, theme=theme)
    if console.no_color:
        console.print(f"{icon} [{word}] {text}")
    else:
        console.print(f"[{style}]{icon} [{word}][/{style}] {text}")
