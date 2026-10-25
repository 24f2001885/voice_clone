"""Terminal UI themes, color palettes, icons, and status badge helpers."""

from dataclasses import dataclass
from typing import Any

from prompt_toolkit.styles import Style as PromptToolkitStyle
import questionary

from voxclone.errors import VoxcloneError

# Unicode Icons
UNICODE_ICONS: dict[str, str] = {
    "cursor": "❯",
    "success": "✔",
    "error": "✖",
    "running": "●",
    "pending": "◌",
    "warning": "⚠",
    "loading": "⇅",
    "paused": "‖",
    "skipped": "–",
}

# ASCII Fallback Icons
ASCII_ICONS: dict[str, str] = {
    "cursor": ">",
    "success": "[OK]",
    "error": "[X]",
    "running": "*",
    "pending": ".",
    "warning": "!",
    "loading": "~",
    "paused": "||",
    "skipped": "-",
}

# Standard Badge Words
BADGE_WORDS: dict[str, str] = {
    "success": "Done",
    "running": "Running",
    "pending": "Waiting",
    "loading": "Loading",
    "warning": "Warning",
    "error": "Failed",
    "paused": "Paused",
    "skipped": "Skipped",
}


@dataclass(frozen=True)
class Theme:
    """Encapsulates color styles, flags, and character glyphs for the CLI."""

    plain: bool
    no_color: bool
    dark: bool

    primary: str
    secondary: str
    success: str
    warning: str
    error: str
    pending: str
    muted: str

    icons: dict[str, str]


def get_theme(plain: bool = False, no_color: bool = False, dark: bool = True) -> Theme:
    """Construct a Theme instance based on terminal capabilities and user preferences."""
    if plain:
        # Plain mode enforces ASCII icons and zero color styling
        return Theme(
            plain=True,
            no_color=True,
            dark=dark,
            primary="",
            secondary="",
            success="",
            warning="",
            error="",
            pending="",
            muted="",
            icons=dict(ASCII_ICONS),
        )

    if no_color:
        # No-color mode keeps Unicode symbols but omits color styling
        return Theme(
            plain=False,
            no_color=True,
            dark=dark,
            primary="",
            secondary="",
            success="",
            warning="",
            error="",
            pending="",
            muted="",
            icons=dict(UNICODE_ICONS),
        )

    # Standard dark or light palette from UX Design Plan
    if dark:
        return Theme(
            plain=False,
            no_color=False,
            dark=True,
            primary="#4FC3F7",
            secondary="#B39DDB",
            success="#66BB6A",
            warning="#FFB74D",
            error="#EF5350",
            pending="#FFD54F",
            muted="#9E9E9E",
            icons=dict(UNICODE_ICONS),
        )

    return Theme(
        plain=False,
        no_color=False,
        dark=False,
        primary="#0277BD",
        secondary="#5E35B1",
        success="#2E7D32",
        warning="#E65100",
        error="#C62828",
        pending="#F9A825",
        muted="#616161",
        icons=dict(UNICODE_ICONS),
    )


def badge(state: str, theme: Theme | None = None) -> tuple[str, str, str]:
    """Return (icon, word, style_name) for a status badge.

    Args:
        state: One of 'success', 'running', 'pending', 'loading', 'warning', 'error', 'paused', 'skipped'.
        theme: Theme configuration (defaults to standard colored theme).

    Returns:
        tuple containing (icon, word, style_string).
    """
    state_key = state.lower()
    if state_key not in BADGE_WORDS:
        raise VoxcloneError(
            f"Unknown badge state '{state}'. Expected one of: {sorted(BADGE_WORDS.keys())}",
            code="VX-900",
        )

    active_theme = theme if theme is not None else get_theme()
    icon = active_theme.icons.get(state_key, "*")
    word = BADGE_WORDS[state_key]

    if active_theme.no_color or active_theme.plain:
        return icon, word, ""

    style_map = {
        "success": f"bold {active_theme.success}",
        "running": f"bold {active_theme.primary}",
        "pending": f"{active_theme.pending}",
        "loading": f"{active_theme.secondary}",
        "warning": f"bold {active_theme.warning}",
        "error": f"bold {active_theme.error}",
        "paused": f"{active_theme.muted}",
        "skipped": f"{active_theme.muted}",
    }
    return icon, word, style_map.get(state_key, "")


def questionary_style(theme: Theme) -> Any:
    """Build a questionary/prompt_toolkit style dictionary from theme colors."""
    if theme.no_color or theme.plain:
        return questionary.Style([])

    return questionary.Style(
        [
            ("qmark", f"fg:{theme.primary} bold"),
            ("question", "bold"),
            ("answer", f"fg:{theme.success} bold"),
            ("pointer", f"fg:{theme.primary} bold"),
            ("highlighted", f"fg:{theme.primary} bold"),
            ("selected", f"fg:{theme.success}"),
            ("separator", f"fg:{theme.muted}"),
            ("instruction", f"fg:{theme.muted}"),
            ("text", ""),
        ]
    )
