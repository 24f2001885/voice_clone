"""Main interactive menu system and questionary prompt wrappers."""

import importlib
from typing import Any

import questionary

from voxclone.errors import VoxcloneError
from voxclone.storage import settings_repo
from voxclone.ui.components import render_error, render_header, render_panel
from voxclone.ui.theme import questionary_style

BACK_LABEL: str = "← Back"

MAIN_MENU_ITEMS: list[tuple[str, str | None]] = [
    ("Text  →  my voice", "voxclone.ui.screens.text_to_voice:screen_text_to_voice"),
    ("Recording  →  my voice", "voxclone.ui.screens.recording_to_voice:screen_recording_to_voice"),
    ("Voice profiles", "voxclone.ui.screens.profiles:screen_profiles"),
    ("Job history", "voxclone.ui.screens.job_history:screen_job_history"),
    ("System", "voxclone.ui.screens.system:screen_system_menu"),
    ("Help", "voxclone.ui.screens.welcome:screen_help"),
    ("About", "voxclone.ui.screens.welcome:screen_about"),
    ("Exit", None),
]


def select(
    state: Any,
    message: str,
    choices: list[str | questionary.Choice],
    default: Any = None,
    allow_back: bool = True,
) -> str | None:
    """Prompt user with interactive selection menu using arrow keys."""
    q_choices = list(choices)
    if allow_back:
        q_choices.append(BACK_LABEL)

    use_filter = len(q_choices) > 7
    q_style = questionary_style(state.theme)

    try:
        ans = questionary.select(
            message=message,
            choices=q_choices,
            default=default,
            style=q_style,
            use_filter=use_filter,
            instruction=" (↑↓ move, Enter select, type to filter)" if use_filter else "",
        ).ask()
        if ans == BACK_LABEL:
            return None
        return ans  # type: ignore[no-any-return]
    except (KeyboardInterrupt, EOFError):
        return None


def text_prompt(
    state: Any,
    message: str,
    default: str = "",
) -> str | None:
    """Prompt user for free-form text input."""
    q_style = questionary_style(state.theme)
    try:
        ans = questionary.text(
            message=message,
            default=default,
            style=q_style,
        ).ask()
        return ans  # type: ignore[no-any-return]
    except (KeyboardInterrupt, EOFError):
        return None


def path_prompt(
    state: Any,
    message: str,
    default: str = "",
) -> str | None:
    """Prompt user for a filesystem path with autocompletion."""
    q_style = questionary_style(state.theme)
    try:
        ans = questionary.path(
            message=message,
            default=default,
            style=q_style,
        ).ask()
        return ans  # type: ignore[no-any-return]
    except (KeyboardInterrupt, EOFError):
        return None


def confirm_prompt(
    state: Any,
    message: str,
    default: bool = True,
) -> bool:
    """Prompt user for a yes/no confirmation."""
    q_style = questionary_style(state.theme)
    try:
        ans = questionary.confirm(
            message=message,
            default=default,
            style=q_style,
        ).ask()
        return bool(ans) if ans is not None else False
    except (KeyboardInterrupt, EOFError):
        return False


def _dispatch_handler(state: Any, dotted_path: str) -> None:
    """Dynamically import and invoke a screen handler function."""
    module_name, func_name = dotted_path.split(":")
    try:
        mod = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        if exc.name == module_name:
            render_panel(
                state.console,
                title="Upcoming Milestone Feature",
                lines=[
                    "This feature arrives in a later milestone.",
                    f"Target module: {module_name}",
                ],
                kind="warning",
                plain=state.plain,
            )
            return
        raise

    handler = getattr(mod, func_name)
    handler(state)


def run_main_menu(state: Any) -> None:
    """Run the primary interactive dropdown loop."""
    # Check first-run hook
    first_run_done = settings_repo.get_setting(state.conn, "first_run_done", default=False)
    if not first_run_done:
        try:
            welcome_mod = importlib.import_module("voxclone.ui.screens.welcome")
            screen_welcome = getattr(welcome_mod, "screen_welcome", None)
            if callable(screen_welcome):
                screen_welcome(state)
        except ModuleNotFoundError:
            pass

    labels = [label for label, _ in MAIN_MENU_ITEMS]
    dispatch_map = {label: path for label, path in MAIN_MENU_ITEMS}

    while True:
        state.console.clear() if not state.plain else None
        render_header(state.console, state)

        if state.plain:
            state.console.print("What would you like to do?")
            state.console.print("Main Menu:")
            for idx, label in enumerate(labels, start=1):
                state.console.print(f"  {idx}. {label}")
        else:
            state.console.print("[dim]↑↓ move   Enter select   Esc back   type to filter[/dim]\n")

        choice = select(
            state=state,
            message="What would you like to do?",
            choices=labels,
            allow_back=False,
        )

        if choice is None or choice == "Exit":
            break

        handler_path = dispatch_map.get(choice)
        if handler_path:
            try:
                _dispatch_handler(state, handler_path)
            except VoxcloneError as err:
                render_error(state.console, err, debug=state.debug, theme=state.theme)
                if not state.plain:
                    questionary.press_any_key_to_continue("Press any key to return to menu...").ask()
            except Exception as exc:
                err = VoxcloneError(f"Unexpected error: {exc!s}", code="VX-900")
                err.__cause__ = exc
                render_error(state.console, err, debug=state.debug, theme=state.theme)
                if not state.plain:
                    questionary.press_any_key_to_continue("Press any key to return to menu...").ask()
