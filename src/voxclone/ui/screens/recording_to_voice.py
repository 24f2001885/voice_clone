"""Recording-to-voice conversion interactive screens (S-30 to S-35)."""
from __future__ import annotations

import logging
from pathlib import Path
import time
from typing import Any

import questionary

from voxclone.audio.io import load_audio, play_audio, record_microphone, save_audio
from voxclone.errors import ConsentRequiredError, VoxcloneError
from voxclone.services.job_service import JobService
from voxclone.ui.components import render_header, render_panel
from voxclone.ui.session import SessionState

logger = logging.getLogger("voxclone.ui.recording_to_voice")


def screen_recording_to_voice(state: SessionState) -> str:
    """Execute recording-to-voice conversion flow: profile pick, input audio, output mode, execution."""
    render_header(state.console, state)
    plain = state.plain

    # 1. Fetch available consenting profiles
    profiles = state.profile_service.list_profiles()
    consenting_profiles = [p for p in profiles if p.consent_confirmed]

    if not consenting_profiles:
        render_panel(
            state.console,
            title="No Consenting Voice Profiles Found",
            lines=[
                "You need at least one enrolled voice profile with ethical consent",
                "to convert recordings into your voice identity.",
                "",
                "Please go to 'Voice profiles' to enroll your first voice.",
            ],
            kind="warning",
            plain=plain,
        )
        if questionary.confirm("Would you like to enroll a new voice now?", default=True).ask():
            return "profiles"
        return "menu"

    # S-30: Select Target Voice Profile
    profile_choices = [
        questionary.Choice(
            title=f"{p.name} ({p.quality_score * 100:.0f}% quality)",
            value=p.id,
        )
        for p in consenting_profiles
    ]
    profile_choices.append(questionary.Choice(title="← Back to main menu", value="back"))

    default_profile_id = state.selected_profile_id or consenting_profiles[0].id

    chosen_profile_id = questionary.select(
        "Select target voice profile for conversion (S-30):",
        choices=profile_choices,
        default=default_profile_id,
    ).ask()

    if not chosen_profile_id or chosen_profile_id == "back":
        return "menu"

    state.selected_profile_id = chosen_profile_id
    selected_profile = next(p for p in consenting_profiles if p.id == chosen_profile_id)
    state.selected_profile_name = selected_profile.name

    # S-31: Input audio source
    source_choice = questionary.select(
        "Select audio input source (S-31):",
        choices=[
            questionary.Choice(title="Select existing audio file (.wav, .mp3, .flac, .m4a)", value="file"),
            questionary.Choice(title="Record speech from microphone now", value="mic"),
            questionary.Choice(title="← Cancel and return", value="cancel"),
        ],
    ).ask()

    if not source_choice or source_choice == "cancel":
        return "menu"

    input_audio_path: Path | None = None

    if source_choice == "file":
        # S-32: File path prompt
        file_path_str = questionary.path(
            "Enter path to source audio recording (S-32):",
            validate=lambda p: Path(p).is_file() or "Audio file does not exist.",
        ).ask()
        if not file_path_str:
            return "menu"
        input_audio_path = Path(file_path_str)
    else:
        # S-33: Microphone recording screen
        render_panel(
            state.console,
            title="Microphone Recording (S-33)",
            lines=[
                "You are about to record a speech passage from your microphone.",
                "Speak naturally into the microphone for 10-30 seconds.",
                "The recording will automatically finish after 20 seconds.",
            ],
            kind="info",
            plain=plain,
        )
        if not questionary.confirm("Ready to start recording?", default=True).ask():
            return "menu"

        state.console.print("[bold red]● Recording from microphone...[/bold red] [dim](speak now)[/dim]")
        try:
            mic_audio, mic_sr = record_microphone(duration_sec=20.0)
            state.console.print("[bold green]✔ Recording complete.[/bold green]")

            # Save temporary mic input under work directory
            mic_file = Path(state.config.work_dir) / f"mic_input_{int(time.time())}.wav"
            mic_file.parent.mkdir(parents=True, exist_ok=True)
            save_audio(mic_audio, mic_sr, mic_file)
            input_audio_path = mic_file
        except Exception as exc:
            render_panel(
                state.console,
                title="Microphone Recording Failed",
                lines=[str(exc)],
                kind="error",
                plain=plain,
            )
            return "menu"

    if not input_audio_path or not input_audio_path.is_file():
        return "menu"

    # Output destination choice
    output_choice = questionary.select(
        "Select output destination:",
        choices=[
            questionary.Choice(title="Save to audio file (.wav)", value="save"),
            questionary.Choice(title="Play through speaker", value="play"),
            questionary.Choice(title="Both (Save and Play)", value="both"),
        ],
        default="save",
    ).ask()

    if not output_choice:
        output_choice = "save"

    # S-34: Execution and parallel progress tracking
    job_service = JobService(
        conn=state.conn,
        config=state.config,
        model_manager=state.model_manager,
    )

    try:
        job = job_service.create_recording_job(
            profile_id=selected_profile.id,
            input_audio_path=input_audio_path,
            output_mode=output_choice,
        )

        render_panel(
            state.console,
            title=f"Starting Voice Conversion (Job: {job.id[:8]})",
            lines=[
                f"Target Profile   : {selected_profile.name}",
                f"Source Audio     : {input_audio_path.name}",
                f"Output Mode      : {output_choice.capitalize()}",
            ],
            kind="info",
            plain=plain,
        )

        last_result = None
        for event in job_service.run_job(job.id):
            if event.stage == "split":
                state.console.print(f"[bold cyan]• Audio Splitter:[/bold cyan] {event.message}")
            elif event.stage == "preparing":
                state.console.print(f"[dim]• CPU Parallel Prep:[/dim] {event.message}")
            elif event.stage == "loading_model":
                state.console.print(f"[bold yellow]• Model Manager:[/bold yellow] {event.message}")
            elif event.stage == "converting":
                idx = (event.chunk_index or 0) + 1
                tot = event.total_chunks or 1
                pct = int((idx / max(1, tot)) * 100)
                state.console.print(f"[green]• GPU Neural Conversion [{idx}/{tot} - {pct}%]:[/green] {event.message}")
            elif event.stage == "postprocessing":
                state.console.print(f"[dim]• CPU Loudness Match:[/dim] {event.message}")
            elif event.stage == "joining":
                state.console.print(f"[bold cyan]• DSP Equal-Power Crossfade:[/bold cyan] {event.message}")
            elif event.stage == "done":
                last_result = event.result
                state.console.print("[bold green]✔ Voice conversion completed successfully![/bold green]")
            elif event.stage in ("failed", "cancelled"):
                state.console.print(f"[bold red]✖ {event.stage.upper()}:[/bold red] {event.message}")

        # S-35: Result Panel
        if last_result and last_result.output_path:
            render_panel(
                state.console,
                title="Conversion Result (S-35)",
                lines=[
                    f"Output File : {last_result.output_path}",
                    f"Duration    : {last_result.duration_sec:.2f} s",
                    f"Sample Rate : {last_result.sample_rate} Hz",
                    f"Elapsed Time: {last_result.elapsed_ms / 1000.0:.2f} s",
                    f"Speed (RTF) : {last_result.real_time_factor:.2f}x",
                ],
                kind="success",
                plain=plain,
            )

            # Post-conversion actions
            while True:
                action = questionary.select(
                    "Result options:",
                    choices=[
                        questionary.Choice(title="Replay converted audio", value="replay"),
                        questionary.Choice(title="Convert another recording", value="again"),
                        questionary.Choice(title="← Return to main menu", value="menu"),
                    ],
                ).ask()

                if action == "replay":
                    try:
                        audio, sr = load_audio(last_result.output_path)
                        play_audio(audio, sr)
                    except Exception as e:
                        state.console.print(f"[yellow]Audio playback failed: {e}[/yellow]")
                elif action == "again":
                    return "recording_to_voice"
                else:
                    break

    except VoxcloneError as err:
        render_panel(
            state.console,
            title=f"Conversion Error: {err.error_code}",
            lines=[str(err), f"Hint: {err.hint}" if hasattr(err, "hint") else ""],
            kind="error",
            plain=plain,
        )
    except Exception as err:
        logger.error("Unexpected error in recording-to-voice screen: %s", err, exc_info=True)
        render_panel(
            state.console,
            title="System Error",
            lines=[str(err)],
            kind="error",
            plain=plain,
        )

    return "menu"
