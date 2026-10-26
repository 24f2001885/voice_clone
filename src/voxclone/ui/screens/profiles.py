"""Voice profile management screens: enrollment, validation, consent, and preview (S-10 to S-17)."""

from pathlib import Path
import time

import questionary
from rich.table import Table

from voxclone.audio.io import list_audio_devices, play_audio
from voxclone.audio.validate import SampleReport
from voxclone.errors import ConsentRequiredError, VoxcloneError
from voxclone.models.profile import VoiceProfile
from voxclone.ui.components import render_header, render_panel
from voxclone.ui.session import SessionState


def show_quality_report(console: Any, report: SampleReport, plain: bool = False) -> None:
    """Render the audio quality and speech presence report (S-13)."""
    if plain:
        console.print("--- Reference Audio Quality Report ---")
        console.print(f"Total Duration : {report.duration_sec:.1f} s")
        console.print(f"Speech Duration: {report.speech_sec:.1f} s (minimum 10.0 s)")
        console.print(f"RMS Level      : {report.rms_dbfs:.1f} dBFS")
        console.print(f"Peak Amplitude : {report.peak:.2f}")
        console.print(f"Clipping Ratio : {report.clipping_ratio * 100:.2f}%")
        console.print(f"Signal-to-Noise: {report.snr_db:.1f} dB")
        console.print(f"Quality Score  : {int(report.quality_score * 100)} / 100")
        console.print(f"Acceptable     : {'YES' if report.acceptable else 'NO'}")
        for note in report.notes:
            console.print(f"  * {note}")
        console.print("---------------------------------------")
        return

    table = Table(title="Audio Quality & Speech Analysis Report (S-13)", box=None, show_header=True)
    table.add_column("Metric", style="bold white", width=22)
    table.add_column("Measured Value", style="cyan", width=18)
    table.add_column("Target Range", style="dim", width=22)
    table.add_column("Status", width=12)

    # Speech duration
    speech_ok = report.speech_sec >= 10.0
    table.add_row(
        "Detected Speech",
        f"{report.speech_sec:.1f} s",
        ">= 10.0 s (20-30s opt)",
        "[bold green]PASS[/bold green]" if speech_ok else "[bold red]FAIL[/bold red]",
    )

    # RMS level
    rms_ok = -32.0 <= report.rms_dbfs <= -12.0
    table.add_row(
        "RMS Energy",
        f"{report.rms_dbfs:.1f} dBFS",
        "-26 to -14 dBFS",
        "[bold green]GOOD[/bold green]" if rms_ok else "[bold yellow]FAIR[/bold yellow]",
    )

    # Clipping
    clip_ok = report.clipping_ratio < 0.005
    table.add_row(
        "Audio Clipping",
        f"{report.clipping_ratio * 100:.2f}%",
        "< 0.5%",
        "[bold green]CLEAN[/bold green]" if clip_ok else "[bold red]CLIPPED[/bold red]",
    )

    # SNR
    snr_ok = report.snr_db >= 15.0
    table.add_row(
        "Signal-to-Noise",
        f"{report.snr_db:.1f} dB",
        ">= 18.0 dB",
        "[bold green]CLEAN[/bold green]" if snr_ok else "[bold yellow]NOISY[/bold yellow]",
    )

    # Quality score
    score_pct = int(report.quality_score * 100)
    score_style = "bold green" if report.quality_score >= 0.7 else ("bold yellow" if report.quality_score >= 0.5 else "bold red")
    table.add_row(
        "Overall Quality",
        f"[{score_style}]{score_pct} / 100[/{score_style}]",
        ">= 50 / 100",
        "[bold green]ACCEPTABLE[/bold green]" if report.acceptable else "[bold red]SUB-PAR[/bold red]",
    )

    console.print(table)

    if report.notes:
        console.print("\n[bold yellow]Analysis Notes & Recommendations:[/bold yellow]")
        for note in report.notes:
            console.print(f"  • {note}")
        console.print("")


def confirm_consent(console: Any, plain: bool = False) -> bool:
    """Enforce explicit ethical voice cloning consent confirmation (S-14, VX-103)."""
    notice = [
        "[bold red]MANDATORY ETHICAL CONSENT DECLARATION (VX-103)[/bold red]",
        "",
        "VoxClone enforces strict ethical boundaries on synthetic voice cloning.",
        "By enrolling this voice reference, you legally certify and affirm that:",
        "",
        "  1. You are the speaker whose voice is recorded, OR",
        "  2. You have obtained explicit, informed, and documented consent from the speaker",
        "     authorizing you to record, clone, and generate synthetic speech from their voice.",
        "  3. You will not use this voice model for deceptive, defamatory, or unlawful purposes.",
        "",
        "This consent event will be cryptographically hashed and timestamped into your local database.",
    ]
    render_panel(console, "Ethical Cloning Consent", notice, kind="warning", plain=plain)

    if plain:
        resp = input("Do you confirm and affirm this declaration? [y/N]: ").strip().lower()
        return resp in ("y", "yes")

    return questionary.confirm(
        "I confirm and affirm that I have valid authorization to clone this voice.",
        default=False,
    ).ask()


def choose_profile(state: SessionState, prompt_text: str = "Select a voice profile:") -> VoiceProfile | None:
    """Interactive selector for picking an existing voice profile."""
    profiles = state.profile_service.list_profiles()
    if not profiles:
        render_panel(
            state.console,
            "No Voice Profiles",
            ["No voice profiles are currently enrolled.", "Enroll a profile from a file or microphone first."],
            kind="warning",
            plain=state.plain,
        )
        if not state.plain:
            questionary.text("Press Enter to continue...", qmark="→").ask()
        else:
            input("Press Enter to continue...")
        return None

    if state.plain:
        state.console.print(f"\n{prompt_text}")
        for idx, p in enumerate(profiles, 1):
            dur_str = f"{p.duration_sec:.1f}s"
            score_str = f"Score: {int(p.quality_score * 100)}%" if p.quality_score is not None else ""
            state.console.print(f"  [{idx}] {p.name} ({dur_str}, {p.source_type}, {score_str})")
        sel = input("Enter choice number (or 'c' to cancel): ").strip()
        if sel.lower() == "c" or not sel.isdigit():
            return None
        idx_val = int(sel) - 1
        if 0 <= idx_val < len(profiles):
            return profiles[idx_val]
        return None

    choices = []
    for p in profiles:
        score_badge = f"[Score: {int(p.quality_score * 100)}%]" if p.quality_score is not None else ""
        choices.append(
            questionary.Choice(
                title=f"{p.name:<20} | {p.duration_sec:>5.1f}s | {p.source_type:<4} | {score_badge}",
                value=p,
            )
        )
    choices.append(questionary.Choice(title="[Cancel]", value=None))

    return questionary.select(prompt_text, choices=choices).ask()


def screen_enroll_file(state: SessionState) -> None:
    """Enroll a voice profile by importing an audio file (S-11)."""
    state.console.clear()
    render_header(state.console, state)

    render_panel(
        state.console,
        "Enroll Profile from File (S-11)",
        [
            "Import an audio file containing 15-30 seconds of clean, continuous speech.",
            "Supported formats: WAV, MP3, FLAC, OGG, M4A.",
        ],
        kind="info",
        plain=state.plain,
    )

    if state.plain:
        path_str = input("Enter path to reference audio file: ").strip()
    else:
        path_str = questionary.path("Enter path to reference audio file:", only_directories=False).ask()

    if not path_str:
        return

    file_path = Path(path_str).expanduser()
    if not file_path.is_file():
        render_panel(
            state.console,
            "File Not Found",
            [f"Audio file '{file_path}' does not exist."],
            kind="error",
            plain=state.plain,
        )
        if not state.plain:
            questionary.text("Press Enter to return...", qmark="→").ask()
        return

    try:
        with state.console.status("[cyan]Analyzing audio sample and verifying speech quality...[/cyan]"):
            prepared = state.profile_service.prepare_from_file(file_path)
    except VoxcloneError as exc:
        render_panel(
            state.console,
            f"Validation Error ({exc.code})",
            [exc.message, f"Hint: {exc.hint}"],
            kind="error",
            plain=state.plain,
        )
        if not state.plain:
            questionary.text("Press Enter to return...", qmark="→").ask()
        return
    except Exception as exc:
        render_panel(
            state.console,
            "Analysis Failed",
            [f"Unexpected error: {exc!s}"],
            kind="error",
            plain=state.plain,
        )
        if not state.plain:
            questionary.text("Press Enter to return...", qmark="→").ask()
        return

    # Render Quality Report (S-13)
    show_quality_report(state.console, prepared.report, plain=state.plain)

    if not prepared.report.acceptable:
        proceed = (
            input("Quality report flagged issues. Do you still wish to proceed? [y/N]: ").strip().lower() in ("y", "yes")
            if state.plain
            else questionary.confirm("Quality report flagged issues. Do you still wish to proceed?", default=False).ask()
        )
        if not proceed:
            return

    # Consent Confirmation Gate (S-14)
    if not confirm_consent(state.console, plain=state.plain):
        render_panel(
            state.console,
            "Enrollment Aborted (VX-103)",
            ["Consent was declined. Profile cannot be created without speaker authorization."],
            kind="error",
            plain=state.plain,
        )
        if not state.plain:
            questionary.text("Press Enter to return...", qmark="→").ask()
        return

    # Profile Name Prompt
    default_name = file_path.stem.replace(" ", "_")[:30]
    while True:
        if state.plain:
            name = input(f"Enter profile name [{default_name}]: ").strip() or default_name
        else:
            name = questionary.text("Enter profile name:", default=default_name).ask()

        if not name:
            return

        try:
            state.profile_service.validate_name(name)
            break
        except Exception as exc:
            state.console.print(f"[bold red]{exc!s}[/bold red]")

    # Commit profile
    try:
        profile = state.profile_service.save_profile(
            name=name,
            prepared=prepared,
            consent_confirmed=True,
        )
        state.selected_profile_id = profile.id
        state.selected_profile_name = profile.name

        render_panel(
            state.console,
            "Voice Profile Enrolled Successfully",
            [
                f"Profile Name    : [bold cyan]{profile.name}[/bold cyan]",
                f"Profile ID      : [dim]{profile.id}[/dim]",
                f"Clean Duration  : {profile.duration_sec:.1f} s @ {profile.sample_rate} Hz",
                f"Quality Score   : {int((profile.quality_score or 0) * 100)} / 100",
                f"Reference Path  : [dim]{profile.reference_path}[/dim]",
                "",
                "[bold green]Set as the active voice profile for speech synthesis and voice conversion.[/bold green]",
            ],
            kind="success",
            plain=state.plain,
        )
        if not state.plain:
            questionary.text("Press Enter to continue...", qmark="→").ask()
        else:
            input("Press Enter to continue...")
    except Exception as exc:
        render_panel(state.console, "Save Failed", [str(exc)], kind="error", plain=state.plain)
        if not state.plain:
            questionary.text("Press Enter to return...", qmark="→").ask()


def screen_enroll_mic(state: SessionState) -> None:
    """Enroll a voice profile by recording live microphone speech (S-12)."""
    state.console.clear()
    render_header(state.console, state)

    devices = list_audio_devices()
    input_devs = devices.get("inputs", [])

    lines = [
        "Record 15 to 30 seconds of your voice reading a natural passage.",
        f"Detected Audio Inputs: {len(input_devs)} device(s) found.",
    ]
    render_panel(state.console, "Enroll Profile from Microphone (S-12)", lines, kind="info", plain=state.plain)

    # Prompt recording duration
    dur_str = "15"
    if state.plain:
        dur_str = input("Recording duration in seconds (10-30) [15]: ").strip() or "15"
    else:
        dur_str = questionary.text("Recording duration in seconds (10-30):", default="15").ask()

    try:
        duration_sec = float(dur_str)
        duration_sec = max(10.0, min(30.0, duration_sec))
    except ValueError:
        duration_sec = 15.0

    state.console.print(f"\n[bold yellow]Preparing to record {duration_sec:.0f} seconds...[/bold yellow]")
    state.console.print("Speak clearly into your microphone at normal conversational volume.\n")

    if not state.plain:
        for count in range(3, 0, -1):
            state.console.print(f"[bold cyan]Recording starts in {count}...[/bold cyan]")
            time.sleep(1.0)
        state.console.print("[bold red]🔴 RECORDING NOW — SPEAK CLEARLY...[/bold red]")
    else:
        input("Press Enter when ready to start recording...")
        state.console.print("RECORDING NOW...")

    try:
        prepared = state.profile_service.prepare_from_mic(duration_sec=duration_sec)
    except VoxcloneError as exc:
        render_panel(
            state.console,
            f"Recording Quality Error ({exc.code})",
            [exc.message, f"Hint: {exc.hint}"],
            kind="error",
            plain=state.plain,
        )
        if not state.plain:
            questionary.text("Press Enter to return...", qmark="→").ask()
        return
    except Exception as exc:
        render_panel(
            state.console,
            "Recording Failed",
            [f"Audio error: {exc!s}"],
            kind="error",
            plain=state.plain,
        )
        if not state.plain:
            questionary.text("Press Enter to return...", qmark="→").ask()
        return

    # Render Quality Report (S-13)
    show_quality_report(state.console, prepared.report, plain=state.plain)

    # Consent Confirmation Gate (S-14)
    if not confirm_consent(state.console, plain=state.plain):
        render_panel(
            state.console,
            "Enrollment Aborted (VX-103)",
            ["Consent was declined. Profile cannot be created without speaker authorization."],
            kind="error",
            plain=state.plain,
        )
        if not state.plain:
            questionary.text("Press Enter to return...", qmark="→").ask()
        return

    # Name Prompt
    while True:
        if state.plain:
            name = input("Enter profile name: ").strip()
        else:
            name = questionary.text("Enter profile name:").ask()

        if not name:
            return

        try:
            state.profile_service.validate_name(name)
            break
        except Exception as exc:
            state.console.print(f"[bold red]{exc!s}[/bold red]")

    # Commit profile
    try:
        profile = state.profile_service.save_profile(
            name=name,
            prepared=prepared,
            consent_confirmed=True,
        )
        state.selected_profile_id = profile.id
        state.selected_profile_name = profile.name

        render_panel(
            state.console,
            "Voice Profile Enrolled Successfully",
            [
                f"Profile Name    : [bold cyan]{profile.name}[/bold cyan]",
                f"Profile ID      : [dim]{profile.id}[/dim]",
                f"Clean Duration  : {profile.duration_sec:.1f} s @ {profile.sample_rate} Hz",
                f"Quality Score   : {int((profile.quality_score or 0) * 100)} / 100",
                "",
                "[bold green]Set as the active voice profile.[/bold green]",
            ],
            kind="success",
            plain=state.plain,
        )
        if not state.plain:
            questionary.text("Press Enter to continue...", qmark="→").ask()
        else:
            input("Press Enter to continue...")
    except Exception as exc:
        render_panel(state.console, "Save Failed", [str(exc)], kind="error", plain=state.plain)
        if not state.plain:
            questionary.text("Press Enter to return...", qmark="→").ask()


def screen_preview(state: SessionState) -> None:
    """Listen to a voice profile's reference audio recording (S-15)."""
    state.console.clear()
    render_header(state.console, state)

    profile = choose_profile(state, prompt_text="Select a voice profile to preview:")
    if profile is None:
        return

    state.console.print(f"\n[cyan]Playing reference audio for profile: [bold]{profile.name}[/bold]...[/cyan]")
    try:
        play_audio(profile.reference_path)
        state.console.print("[green]Playback finished.[/green]")
    except Exception as exc:
        state.console.print(f"[bold red]Playback failed: {exc!s}[/bold red]")

    if not state.plain:
        questionary.text("Press Enter to continue...", qmark="→").ask()
    else:
        input("Press Enter to continue...")


def screen_rename(state: SessionState) -> None:
    """Rename an existing voice profile (S-16)."""
    state.console.clear()
    render_header(state.console, state)

    profile = choose_profile(state, prompt_text="Select a profile to rename:")
    if profile is None:
        return

    while True:
        if state.plain:
            new_name = input(f"Enter new name for '{profile.name}': ").strip()
        else:
            new_name = questionary.text(f"Enter new name for '{profile.name}':", default=profile.name).ask()

        if not new_name or new_name == profile.name:
            return

        try:
            updated = state.profile_service.rename_profile(profile.id, new_name)
            if state.selected_profile_id == profile.id:
                state.selected_profile_name = updated.name
            render_panel(
                state.console,
                "Profile Renamed",
                [f"Profile renamed from '{profile.name}' to '[bold cyan]{updated.name}[/bold cyan]'."],
                kind="success",
                plain=state.plain,
            )
            if not state.plain:
                questionary.text("Press Enter to continue...", qmark="→").ask()
            else:
                input("Press Enter to continue...")
            break
        except Exception as exc:
            state.console.print(f"[bold red]{exc!s}[/bold red]")


def screen_delete(state: SessionState) -> None:
    """Permanently delete an enrolled voice profile and its audio file (S-17)."""
    state.console.clear()
    render_header(state.console, state)

    profile = choose_profile(state, prompt_text="Select a profile to permanently delete:")
    if profile is None:
        return

    if state.plain:
        confirm = input(f"Permanently delete voice profile '{profile.name}'? [y/N]: ").strip().lower() in ("y", "yes")
    else:
        confirm = questionary.confirm(
            f"Are you sure you want to permanently delete profile '{profile.name}'?",
            default=False,
        ).ask()

    if not confirm:
        return

    try:
        state.profile_service.delete_profile(profile.id)
        if state.selected_profile_id == profile.id:
            state.selected_profile_id = None
            state.selected_profile_name = None

        render_panel(
            state.console,
            "Profile Deleted",
            [f"Voice profile '{profile.name}' and reference WAV deleted."],
            kind="success",
            plain=state.plain,
        )
        if not state.plain:
            questionary.text("Press Enter to continue...", qmark="→").ask()
        else:
            input("Press Enter to continue...")
    except Exception as exc:
        render_panel(state.console, "Delete Failed", [str(exc)], kind="error", plain=state.plain)
        if not state.plain:
            questionary.text("Press Enter to return...", qmark="→").ask()


def screen_select_active(state: SessionState) -> None:
    """Set the currently active voice profile for conversion and synthesis."""
    state.console.clear()
    render_header(state.console, state)

    profile = choose_profile(state, prompt_text="Choose active voice profile:")
    if profile is not None:
        state.selected_profile_id = profile.id
        state.selected_profile_name = profile.name
        render_panel(
            state.console,
            "Active Profile Updated",
            [f"Active profile set to: [bold cyan]{profile.name}[/bold cyan]"],
            kind="success",
            plain=state.plain,
        )
        if not state.plain:
            questionary.text("Press Enter to continue...", qmark="→").ask()
        else:
            input("Press Enter to continue...")


def screen_list_profiles(state: SessionState) -> None:
    """Display tabular list of all enrolled voice profiles."""
    state.console.clear()
    render_header(state.console, state)

    profiles = state.profile_service.list_profiles()
    if not profiles:
        render_panel(
            state.console,
            "No Voice Profiles Enrolled",
            ["No voice profiles found.", "Select 'Enroll from file' or 'Enroll from microphone'."],
            kind="info",
            plain=state.plain,
        )
        if not state.plain:
            questionary.text("Press Enter to return...", qmark="→").ask()
        else:
            input("Press Enter to return...")
        return

    if state.plain:
        state.console.print("--- Enrolled Voice Profiles ---")
        for p in profiles:
            active_mark = " (ACTIVE)" if p.id == state.selected_profile_id else ""
            score = f"{int(p.quality_score * 100)}%" if p.quality_score is not None else "n/a"
            state.console.print(f"* {p.name}{active_mark}: {p.duration_sec:.1f}s | {p.source_type} | Quality: {score} | ID: {p.id}")
        input("\nPress Enter to return...")
        return

    table = Table(title="Enrolled Voice Profiles", box=None, show_header=True)
    table.add_column("Status", width=8)
    table.add_column("Name", style="bold white", width=22)
    table.add_column("Duration", style="cyan", width=12)
    table.add_column("Source", style="dim", width=10)
    table.add_column("Quality", style="green", width=12)
    table.add_column("Enrolled Date", style="dim", width=22)

    for p in profiles:
        is_active = p.id == state.selected_profile_id
        active_badge = "[bold cyan]ACTIVE[/bold cyan]" if is_active else ""
        quality_str = f"{int(p.quality_score * 100)} / 100" if p.quality_score is not None else "n/a"
        date_str = p.created_at[:19].replace("T", " ")
        table.add_row(
            active_badge,
            p.name,
            f"{p.duration_sec:.1f} s",
            p.source_type,
            quality_str,
            date_str,
        )

    state.console.print(table)
    state.console.print("")
    questionary.text("Press Enter to return...", qmark="→").ask()


def screen_profiles(state: SessionState) -> None:
    """Voice Profiles hub menu (S-10)."""
    while True:
        state.console.clear()
        render_header(state.console, state)

        if state.plain:
            state.console.print("\n=== Voice Profiles Menu (S-10) ===")
            state.console.print("  [1] List Voice Profiles")
            state.console.print("  [2] Enroll from Audio File")
            state.console.print("  [3] Enroll from Microphone")
            state.console.print("  [4] Select Active Profile")
            state.console.print("  [5] Preview Profile Audio")
            state.console.print("  [6] Rename Profile")
            state.console.print("  [7] Delete Profile")
            state.console.print("  [8] Back to Main Menu")
            choice = input("Enter choice [1-8]: ").strip()
            if choice == "1":
                screen_list_profiles(state)
            elif choice == "2":
                screen_enroll_file(state)
            elif choice == "3":
                screen_enroll_mic(state)
            elif choice == "4":
                screen_select_active(state)
            elif choice == "5":
                screen_preview(state)
            elif choice == "6":
                screen_rename(state)
            elif choice == "7":
                screen_delete(state)
            elif choice in ("8", "q", "back"):
                break
            continue

        choices = [
            questionary.Choice(title="1. List Voice Profiles", value="list"),
            questionary.Choice(title="2. Enroll from Audio File (S-11)", value="enroll_file"),
            questionary.Choice(title="3. Enroll from Microphone (S-12)", value="enroll_mic"),
            questionary.Choice(title="4. Select Active Profile", value="select_active"),
            questionary.Choice(title="5. Preview Profile Audio (S-15)", value="preview"),
            questionary.Choice(title="6. Rename Profile (S-16)", value="rename"),
            questionary.Choice(title="7. Delete Profile (S-17)", value="delete"),
            questionary.Choice(title="8. Back to Main Menu", value="back"),
        ]

        action = questionary.select("Voice Profiles:", choices=choices).ask()
        if action in (None, "back"):
            break
        elif action == "list":
            screen_list_profiles(state)
        elif action == "enroll_file":
            screen_enroll_file(state)
        elif action == "enroll_mic":
            screen_enroll_mic(state)
        elif action == "select_active":
            screen_select_active(state)
        elif action == "preview":
            screen_preview(state)
        elif action == "rename":
            screen_rename(state)
        elif action == "delete":
            screen_delete(state)
