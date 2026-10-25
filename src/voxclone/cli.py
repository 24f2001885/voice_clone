"""Command-line interface entry points and sub-commands using Typer."""

from dataclasses import dataclass
import sys
from typing import Annotated

import typer

from voxclone.errors import InternalError, VoxcloneError
from voxclone.services.system_service import get_storage_report, run_doctor
from voxclone.storage.migrate import apply_migrations, current_version
from voxclone.ui import menu, session
from voxclone.ui.components import make_console, render_error, render_table
from voxclone.ui.theme import badge, get_theme

app = typer.Typer(
    name="voxclone",
    help="VoxClone: Zero-shot voice cloning and synthesis terminal application",
    add_completion=False,
    no_args_is_help=False,
)

system_app = typer.Typer(
    name="system",
    help="System diagnostics, storage inspections, and database administration",
    no_args_is_help=True,
)
app.add_typer(system_app)


@dataclass
class CliContext:
    """Carries CLI flag overrides."""

    plain: bool = False
    debug: bool = False


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    plain: Annotated[
        bool,
        typer.Option("--plain", help="Run with monochrome ASCII output and no box-drawing borders"),
    ] = False,
    debug: Annotated[
        bool,
        typer.Option("--debug", help="Enable verbose debug logging and stack trace output on error"),
    ] = False,
) -> None:
    """Launch VoxClone interactive dropdown menu or execute sub-command."""
    cli_ctx = CliContext(plain=plain, debug=debug)
    ctx.obj = cli_ctx

    if ctx.invoked_subcommand is None:
        state = None
        try:
            state = session.bootstrap(debug=debug, plain=plain)
            menu.run_main_menu(state)
        except KeyboardInterrupt:
            console = make_console(get_theme(plain=plain), plain=plain)
            console.print("\nOperation cancelled by user.")
            sys.exit(130)
        except VoxcloneError as err:
            console = make_console(get_theme(plain=plain), plain=plain)
            render_error(console, err, debug=debug)
            sys.exit(1)
        except Exception as exc:
            console = make_console(get_theme(plain=plain), plain=plain)
            err = InternalError(f"Unexpected error: {exc!s}")
            err.__cause__ = exc
            render_error(console, err, debug=debug)
            sys.exit(1)
        finally:
            if state is not None:
                session.close(state)


@system_app.command("doctor")
def system_doctor(
    ctx: typer.Context,
    plain: Annotated[
        bool,
        typer.Option("--plain", help="Force ASCII output format"),
    ] = False,
    debug: Annotated[
        bool,
        typer.Option("--debug", help="Show debug information"),
    ] = False,
) -> None:
    """Run system and container pre-flight diagnostics."""
    cli_ctx: CliContext = ctx.find_root().obj or CliContext(plain=plain, debug=debug)
    is_plain = plain or cli_ctx.plain
    is_debug = debug or cli_ctx.debug

    state = None
    try:
        state = session.bootstrap(debug=is_debug, plain=is_plain)
        checks = run_doctor(state.config)

        columns = ["Check", "Status", "Detail", "Fix Hint"]
        rows: list[list[str]] = []
        for chk in checks:
            icon, word, _ = badge("success" if chk.ok else "error", theme=state.theme)
            rows.append([chk.name, f"{icon} {word}", chk.detail, chk.fix_hint or "-"])

        render_table(
            console=state.console,
            title="System Doctor Diagnostics",
            columns=columns,
            rows=rows,
            plain=state.plain,
        )
    except VoxcloneError as err:
        console = make_console(get_theme(plain=is_plain), plain=is_plain)
        render_error(console, err, debug=is_debug)
        sys.exit(1)
    except Exception as exc:
        console = make_console(get_theme(plain=is_plain), plain=is_plain)
        err = InternalError(f"Doctor diagnostic failed: {exc!s}")
        err.__cause__ = exc
        render_error(console, err, debug=is_debug)
        sys.exit(1)
    finally:
        if state is not None:
            session.close(state)


@system_app.command("storage")
def system_storage(
    ctx: typer.Context,
    plain: Annotated[
        bool,
        typer.Option("--plain", help="Force ASCII output format"),
    ] = False,
    debug: Annotated[
        bool,
        typer.Option("--debug", help="Show debug information"),
    ] = False,
) -> None:
    """Inspect disk space consumed by profiles, outputs, models, and work dirs."""
    cli_ctx: CliContext = ctx.find_root().obj or CliContext(plain=plain, debug=debug)
    is_plain = plain or cli_ctx.plain
    is_debug = debug or cli_ctx.debug

    state = None
    try:
        state = session.bootstrap(debug=is_debug, plain=is_plain)
        report = get_storage_report(state.config)

        columns = ["Storage Tier", "Disk Space (MB)"]
        rows = [
            ["Voice Profiles (profiles/)", f"{report.profiles_mb:.2f} MB"],
            ["Generated Audio (outputs/)", f"{report.outputs_mb:.2f} MB"],
            ["HuggingFace Cache (/models)", f"{report.models_mb:.2f} MB"],
            ["Temporary Work Dirs (work/)", f"{report.work_mb:.2f} MB"],
        ]

        render_table(
            console=state.console,
            title="Storage Utilization Report",
            columns=columns,
            rows=rows,
            plain=state.plain,
        )
    except VoxcloneError as err:
        console = make_console(get_theme(plain=is_plain), plain=is_plain)
        render_error(console, err, debug=is_debug)
        sys.exit(1)
    except Exception as exc:
        console = make_console(get_theme(plain=is_plain), plain=is_plain)
        err = InternalError(f"Storage report failed: {exc!s}")
        err.__cause__ = exc
        render_error(console, err, debug=is_debug)
        sys.exit(1)
    finally:
        if state is not None:
            session.close(state)


@system_app.command("migrate")
def system_migrate(
    ctx: typer.Context,
    plain: Annotated[
        bool,
        typer.Option("--plain", help="Force ASCII output format"),
    ] = False,
    debug: Annotated[
        bool,
        typer.Option("--debug", help="Show debug information"),
    ] = False,
) -> None:
    """Apply any pending SQLite schema migrations."""
    cli_ctx: CliContext = ctx.find_root().obj or CliContext(plain=plain, debug=debug)
    is_plain = plain or cli_ctx.plain
    is_debug = debug or cli_ctx.debug

    state = None
    try:
        state = session.bootstrap(debug=is_debug, plain=is_plain)
        v_current = current_version(state.conn)
        applied = apply_migrations(state.conn, state.config.migrations_dir)
        console = state.console
        if applied:
            console.print(f"Applied migrations: {', '.join(f'{v:03d}' for v in applied)}")
            console.print(f"Current database version: {current_version(state.conn):03d}")
        else:
            console.print(f"Database schema is up to date (version {v_current:03d}).")
    except VoxcloneError as err:
        console = make_console(get_theme(plain=is_plain), plain=is_plain)
        render_error(console, err, debug=is_debug)
        sys.exit(1)
    except Exception as exc:
        console = make_console(get_theme(plain=is_plain), plain=is_plain)
        err = InternalError(f"Migration execution failed: {exc!s}")
        err.__cause__ = exc
        render_error(console, err, debug=is_debug)
        sys.exit(1)
    finally:
        if state is not None:
            session.close(state)
