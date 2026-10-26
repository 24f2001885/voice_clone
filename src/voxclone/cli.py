"""Command-line interface entry points and sub-commands using Typer."""

from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Annotated

import typer

from voxclone.errors import InternalError, VoxcloneError
from voxclone.services.system_service import get_storage_report, run_doctor
from voxclone.services.job_service import JobService
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

profiles_app = typer.Typer(
    name="profiles",
    help="Voice profile enrollment, listing, inspection, and lifecycle management",
    no_args_is_help=True,
)
app.add_typer(profiles_app)


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


@system_app.command("free-gpu")
def system_free_gpu(
    ctx: typer.Context,
    plain: Annotated[bool, typer.Option("--plain", help="Force ASCII output format")] = False,
    debug: Annotated[bool, typer.Option("--debug", help="Show debug information")] = False,
) -> None:
    """Manually unload resident neural models and clear PyTorch CUDA caches."""
    cli_ctx: CliContext = ctx.find_root().obj or CliContext(plain=plain, debug=debug)
    is_plain = plain or cli_ctx.plain
    is_debug = debug or cli_ctx.debug

    state = None
    try:
        state = session.bootstrap(debug=is_debug, plain=is_plain)
        res = state.model_service.free_gpu_memory()
        unloaded = res.get("unloaded_key") or "(none)"
        freed = res.get("freed_mb")
        free_now = res.get("free_now_mb")
        state.console.print(f"Unloaded resident model: {unloaded}")
        if freed is not None:
            state.console.print(f"Reclaimed VRAM: +{freed} MB")
        if free_now is not None:
            state.console.print(f"Current free VRAM: {free_now} MB")
    except VoxcloneError as err:
        console = make_console(get_theme(plain=is_plain), plain=is_plain)
        render_error(console, err, debug=is_debug)
        sys.exit(1)
    except Exception as exc:
        console = make_console(get_theme(plain=is_plain), plain=is_plain)
        err = InternalError(f"Free GPU command failed: {exc!s}")
        err.__cause__ = exc
        render_error(console, err, debug=is_debug)
        sys.exit(1)
    finally:
        if state is not None:
            session.close(state)


@system_app.command("fetch-models")
def system_fetch_models(
    ctx: typer.Context,
    keys: Annotated[list[str] | None, typer.Option("--key", "-k", help="Specific model keys ('tts', 'vc', 'emotion')")] = None,
    plain: Annotated[bool, typer.Option("--plain", help="Force ASCII output format")] = False,
    debug: Annotated[bool, typer.Option("--debug", help="Show debug information")] = False,
) -> None:
    """Verify or download required neural model weights from Hugging Face."""
    from voxclone.services.system_service import fetch_models

    cli_ctx: CliContext = ctx.find_root().obj or CliContext(plain=plain, debug=debug)
    is_plain = plain or cli_ctx.plain
    is_debug = debug or cli_ctx.debug

    state = None
    try:
        state = session.bootstrap(debug=is_debug, plain=is_plain)
        results = fetch_models(state.config, keys=keys)
        columns = ["Model Key", "Repository", "Status", "Detail"]
        rows = []
        for r in results:
            rows.append([r.model_key, r.repo_id, "OK" if r.ok else "FAIL", r.detail])
        render_table(
            console=state.console,
            title="Model Weights Verification",
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
        err = InternalError(f"Fetch models failed: {exc!s}")
        err.__cause__ = exc
        render_error(console, err, debug=is_debug)
        sys.exit(1)
    finally:
        if state is not None:
            session.close(state)


@system_app.command("status")
def system_status(
    ctx: typer.Context,
    plain: Annotated[bool, typer.Option("--plain", help="Force ASCII output format")] = False,
    debug: Annotated[bool, typer.Option("--debug", help="Show debug information")] = False,
) -> None:
    """Inspect active neural model residency and VRAM status."""
    cli_ctx: CliContext = ctx.find_root().obj or CliContext(plain=plain, debug=debug)
    is_plain = plain or cli_ctx.plain
    is_debug = debug or cli_ctx.debug

    state = None
    try:
        state = session.bootstrap(debug=is_debug, plain=is_plain)
        status = state.model_service.get_status()
        state.console.print(f"Resident Model : {status.resident_key or '(none)'}")
        state.console.print(f"Compute Device : {status.device}")
        state.console.print(f"VRAM Free      : {status.vram_free_mb if status.vram_free_mb is not None else 'n/a'} MB")
        state.console.print(f"VRAM Total     : {status.vram_total_mb if status.vram_total_mb is not None else 'n/a'} MB")
        state.console.print(f"Engine Mode    : {status.engine_mode}")
        state.console.print(f"Keep-Warm      : {status.keep_warm}")
    except VoxcloneError as err:
        console = make_console(get_theme(plain=is_plain), plain=is_plain)
        render_error(console, err, debug=is_debug)
        sys.exit(1)
    finally:
        if state is not None:
            session.close(state)


@profiles_app.command("list")
def profiles_list(
    ctx: typer.Context,
    plain: Annotated[bool, typer.Option("--plain", help="Force ASCII output format")] = False,
    debug: Annotated[bool, typer.Option("--debug", help="Show debug information")] = False,
) -> None:
    """List all registered voice profiles."""
    cli_ctx: CliContext = ctx.find_root().obj or CliContext(plain=plain, debug=debug)
    is_plain = plain or cli_ctx.plain
    is_debug = debug or cli_ctx.debug

    state = None
    try:
        state = session.bootstrap(debug=is_debug, plain=is_plain)
        profiles = state.profile_service.list_profiles()
        if not profiles:
            state.console.print("No voice profiles registered.")
            return

        columns = ["ID", "Name", "Duration", "Source", "Quality", "Created At"]
        rows = []
        for p in profiles:
            score = f"{int(p.quality_score * 100)}%" if p.quality_score is not None else "n/a"
            rows.append([p.id[:8], p.name, f"{p.duration_sec:.1f}s", p.source_type, score, p.created_at[:19]])

        render_table(
            console=state.console,
            title="Registered Voice Profiles",
            columns=columns,
            rows=rows,
            plain=state.plain,
        )
    except VoxcloneError as err:
        console = make_console(get_theme(plain=is_plain), plain=is_plain)
        render_error(console, err, debug=is_debug)
        sys.exit(1)
    finally:
        if state is not None:
            session.close(state)


@profiles_app.command("enroll")
def profiles_enroll(
    ctx: typer.Context,
    name: Annotated[str, typer.Option("--name", "-n", help="Unique voice profile name")],
    file: Annotated[str | None, typer.Option("--file", "-f", help="Path to reference audio file")] = None,
    mic: Annotated[bool, typer.Option("--mic", "-m", help="Record reference speech from microphone")] = False,
    duration: Annotated[float, typer.Option("--duration", "-d", help="Recording duration in seconds (10-30s)")] = 15.0,
    consent: Annotated[bool, typer.Option("--consent/--no-consent", help="Confirm ethical speaker consent (VX-103 mandatory)")] = False,
    plain: Annotated[bool, typer.Option("--plain", help="Force ASCII output format")] = False,
    debug: Annotated[bool, typer.Option("--debug", help="Show debug information")] = False,
) -> None:
    """Enroll a new voice profile from an audio file or microphone recording."""
    from pathlib import Path
    from voxclone.errors import ConsentRequiredError

    cli_ctx: CliContext = ctx.find_root().obj or CliContext(plain=plain, debug=debug)
    is_plain = plain or cli_ctx.plain
    is_debug = debug or cli_ctx.debug

    if not consent:
        console = make_console(get_theme(plain=is_plain), plain=is_plain)
        err = ConsentRequiredError(
            "Consent confirmation is mandatory to enroll a voice profile (--consent required).",
            hint="Pass --consent flag to certify you have explicit authorization to clone this voice.",
        )
        render_error(console, err, debug=is_debug)
        sys.exit(1)

    if not file and not mic:
        console = make_console(get_theme(plain=is_plain), plain=is_plain)
        err = InternalError("Must provide either --file <path> or --mic to enroll a voice profile.")
        render_error(console, err, debug=is_debug)
        sys.exit(1)

    state = None
    try:
        state = session.bootstrap(debug=is_debug, plain=is_plain)
        if file:
            prepared = state.profile_service.prepare_from_file(Path(file))
        else:
            prepared = state.profile_service.prepare_from_mic(duration_sec=duration)

        profile = state.profile_service.save_profile(
            name=name,
            prepared=prepared,
            consent_confirmed=True,
        )
        state.console.print(f"Profile '{profile.name}' enrolled successfully.")
        state.console.print(f"ID: {profile.id} | Duration: {profile.duration_sec:.1f}s | Quality Score: {int((profile.quality_score or 0) * 100)}%")
    except VoxcloneError as err:
        console = make_console(get_theme(plain=is_plain), plain=is_plain)
        render_error(console, err, debug=is_debug)
        sys.exit(1)
    finally:
        if state is not None:
            session.close(state)


@profiles_app.command("preview")
def profiles_preview(
    identifier: Annotated[str, typer.Argument(help="Voice profile ID or exact name")],
    ctx: typer.Context,
    plain: Annotated[bool, typer.Option("--plain", help="Force ASCII output format")] = False,
    debug: Annotated[bool, typer.Option("--debug", help="Show debug information")] = False,
) -> None:
    """Play reference audio of an enrolled voice profile."""
    from voxclone.audio.io import play_audio

    cli_ctx: CliContext = ctx.find_root().obj or CliContext(plain=plain, debug=debug)
    is_plain = plain or cli_ctx.plain
    is_debug = debug or cli_ctx.debug

    state = None
    try:
        state = session.bootstrap(debug=is_debug, plain=is_plain)
        profile_path = state.profile_service.preview_profile(identifier)
        state.console.print(f"Playing reference audio: {profile_path}")
        play_audio(profile_path)
    except VoxcloneError as err:
        console = make_console(get_theme(plain=is_plain), plain=is_plain)
        render_error(console, err, debug=is_debug)
        sys.exit(1)
    finally:
        if state is not None:
            session.close(state)


@profiles_app.command("rename")
def profiles_rename(
    identifier: Annotated[str, typer.Argument(help="Voice profile ID or exact name")],
    new_name: Annotated[str, typer.Argument(help="New profile name")],
    ctx: typer.Context,
    plain: Annotated[bool, typer.Option("--plain", help="Force ASCII output format")] = False,
    debug: Annotated[bool, typer.Option("--debug", help="Show debug information")] = False,
) -> None:
    """Rename an existing voice profile."""
    cli_ctx: CliContext = ctx.find_root().obj or CliContext(plain=plain, debug=debug)
    is_plain = plain or cli_ctx.plain
    is_debug = debug or cli_ctx.debug

    state = None
    try:
        state = session.bootstrap(debug=is_debug, plain=is_plain)
        profile = state.profile_service.get_profile(identifier)
        updated = state.profile_service.rename_profile(profile.id, new_name)
        state.console.print(f"Voice profile renamed to '{updated.name}'.")
    except VoxcloneError as err:
        console = make_console(get_theme(plain=is_plain), plain=is_plain)
        render_error(console, err, debug=is_debug)
        sys.exit(1)
    finally:
        if state is not None:
            session.close(state)


@profiles_app.command("delete")
def profiles_delete(
    identifier: Annotated[str, typer.Argument(help="Voice profile ID or exact name")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation prompt")] = False,
    ctx: typer.Context = None,  # type: ignore[assignment]
    plain: Annotated[bool, typer.Option("--plain", help="Force ASCII output format")] = False,
    debug: Annotated[bool, typer.Option("--debug", help="Show debug information")] = False,
) -> None:
    """Delete an enrolled voice profile and its reference audio file."""
    cli_ctx: CliContext = (ctx.find_root().obj if ctx else None) or CliContext(plain=plain, debug=debug)
    is_plain = plain or cli_ctx.plain
    is_debug = debug or cli_ctx.debug

    state = None
    try:
        state = session.bootstrap(debug=is_debug, plain=is_plain)
        profile = state.profile_service.get_profile(identifier)
        if not yes:
            confirm = input(f"Are you sure you want to delete profile '{profile.name}'? [y/N]: ").strip().lower()
            if confirm not in ("y", "yes"):
                state.console.print("Deletion aborted.")
                return

        state.profile_service.delete_profile(profile.id)
        state.console.print(f"Voice profile '{profile.name}' deleted.")
    except VoxcloneError as err:
        console = make_console(get_theme(plain=is_plain), plain=is_plain)
        render_error(console, err, debug=is_debug)
        sys.exit(1)
    finally:
        if state is not None:
            session.close(state)


@app.command("speak")
def speak(
    profile: Annotated[str, typer.Option("--profile", "-p", help="Target voice profile name or ID")],
    text: Annotated[str | None, typer.Option("--text", "-t", help="Text passage to synthesize")] = None,
    text_file: Annotated[Path | None, typer.Option("--text-file", "-f", help="Path to .txt file")] = None,
    emotion: Annotated[str, typer.Option("--emotion", "-e", help="Emotion style [calm|normal|expressive]")] = "normal",
    save: Annotated[bool, typer.Option("--save", help="Save output to audio file (.wav)")] = False,
    play: Annotated[bool, typer.Option("--play", help="Play output audio")] = False,
    both: Annotated[bool, typer.Option("--both", help="Save output to file and play")] = False,
    plain: Annotated[bool, typer.Option("--plain", help="Force ASCII output format")] = False,
    debug: Annotated[bool, typer.Option("--debug", help="Show debug information")] = False,
    ctx: typer.Context = None,  # type: ignore[assignment]
) -> None:
    """Synthesize text into speech using an enrolled voice profile."""
    cli_ctx: CliContext = (ctx.find_root().obj if ctx else None) or CliContext(plain=plain, debug=debug)
    is_plain = plain or cli_ctx.plain
    is_debug = debug or cli_ctx.debug

    if (text is None and text_file is None) or (text is not None and text_file is not None):
        console = make_console(get_theme(plain=is_plain), plain=is_plain)
        console.print("Error: Exactly one of --text or --text-file must be provided.")
        sys.exit(1)

    input_text = text or ""
    if text_file is not None:
        if not text_file.is_file():
            console = make_console(get_theme(plain=is_plain), plain=is_plain)
            console.print(f"Error: Text file not found: {text_file}")
            sys.exit(1)
        input_text = text_file.read_text(encoding="utf-8")

    output_mode = "save"
    if both:
        output_mode = "both"
    elif play:
        output_mode = "play"
    elif save:
        output_mode = "save"

    state = None
    try:
        state = session.bootstrap(debug=is_debug, plain=is_plain)
        try:
            prof = state.profile_service.get_profile(profile)
        except Exception:
            console = make_console(get_theme(plain=is_plain), plain=is_plain)
            console.print(f"Error: Voice profile '{profile}' not found. Run 'voxclone profiles enroll' first.")
            sys.exit(1)

        job_service = JobService(
            conn=state.conn,
            config=state.config,
            model_manager=state.model_manager,
        )
        job = job_service.create_text_job(
            profile_id=prof.id,
            input_text=input_text,
            emotion_mode=emotion,
            output_mode=output_mode,
        )

        for event in job_service.run_job(job.id):
            if is_plain:
                state.console.print(f"[{event.stage}] {event.message}")
            else:
                state.console.print(f"• [cyan]{event.stage}:[/cyan] {event.message}")
            if event.stage == "done" and event.result and event.result.output_path:
                state.console.print(f"Output generated: {event.result.output_path}")
            elif event.stage in ("failed", "cancelled"):
                sys.exit(1)
    except VoxcloneError as err:
        console = make_console(get_theme(plain=is_plain), plain=is_plain)
        render_error(console, err, debug=is_debug)
        sys.exit(1)
    finally:
        if state is not None:
            session.close(state)


