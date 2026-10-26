"""Text-to-voice interactive screens (S-20 to S-26) with emotion classification and preview."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import questionary
from rich.table import Table

from voxclone.audio.io import load_audio, play_audio
from voxclone.errors import ConsentRequiredError, VoxcloneError
from voxclone.pipelines.emotion_mapping import map_emotion_label
from voxclone.pipelines.text_splitter import split_text_into_chunks
from voxclone.services.job_service import JobService
from voxclone.ui.components import render_header, render_panel
from voxclone.ui.session import SessionState

logger = logging.getLogger("voxclone.ui.text_to_voice")


def screen_text_to_voice(state: SessionState) -> str:
    """Execute text-to-voice workflow: profile pick, text input, emotion, output, and execution."""
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
                "to synthesize speech in your voice.",
                "",
                "Please go to 'Voice profiles' to enroll your first voice.",
            ],
            kind="warning",
            plain=plain,
        )
        if questionary.confirm("Would you like to enroll a new voice now?", default=True).ask():
            return "profiles"
        return "menu"

    # S-20: Select Voice Profile
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
        "Select voice profile for synthesis (S-20):",
        choices=profile_choices,
        default=default_profile_id,
    ).ask()

    if not chosen_profile_id or chosen_profile_id == "back":
        return "menu"

    state.selected_profile_id = chosen_profile_id
    selected_profile = next(p for p in consenting_profiles if p.id == chosen_profile_id)
    state.selected_profile_name = selected_profile.name

    # S-21: Input text source
    source_choice = questionary.select(
        "How would you like to provide the text? (S-21)",
        choices=[
            questionary.Choice(title="Type text directly in terminal", value="type"),
            questionary.Choice(title="Read text from a local .txt file", value="file"),
            questionary.Choice(title="← Cancel and return", value="cancel"),
        ],
    ).ask()

    if not source_choice or source_choice == "cancel":
        return "menu"

    input_text = ""
    if source_choice == "type":
        input_text = questionary.text(
            "Enter text to synthesize:",
            validate=lambda t: len(t.strip()) > 0 or "Text cannot be empty.",
        ).ask()
    else:
        file_path_str = questionary.path(
            "Enter path to .txt file:",
            validate=lambda p: Path(p).is_file() or "File does not exist.",
        ).ask()
        if not file_path_str:
            return "menu"
        try:
            input_text = Path(file_path_str).read_text(encoding="utf-8").strip()
        except Exception as e:
            render_panel(
                state.console,
                title="File Read Error",
                lines=[f"Failed reading text file: {e}"],
                kind="error",
                plain=plain,
            )
            return "menu"

    if not input_text:
        return "menu"

    # S-22: Emotion selection
    emotion_choice = questionary.select(
        "Select emotional delivery style (S-22):",
        choices=[
            questionary.Choice(title="Auto (Detect emotion from text passages)", value="auto"),
            questionary.Choice(title="Normal (balanced, steady cadence)", value="normal"),
            questionary.Choice(title="Calm (relaxed, lower dynamics)", value="calm"),
            questionary.Choice(title="Expressive (higher energy and dynamics)", value="expressive"),
        ],
        default="auto",
    ).ask()

    if not emotion_choice:
        emotion_choice = "auto"

    # S-23: Emotion preview table (when auto mode is selected)
    if emotion_choice == "auto":
        max_chars = int(state.config.sentence_max_chars if hasattr(state.config, "sentence_max_chars") else 200)
        chunks = split_text_into_chunks(input_text, max_chars=max_chars)

        state.console.print("\n[dim]Analyzing text emotion across passages...[/dim]")
        try:
            emotion_engine = state.model_manager.acquire("emotion")
            detected_labels = emotion_engine.classify(chunks)
            state.model_manager.unload("emotion")

            table = Table(title="Emotion Analysis Preview (S-23)", expand=False)
            table.add_column("#", justify="right", style="cyan")
            table.add_column("Text Passage", style="white")
            table.add_column("Detected Emotion", style="bold green")
            table.add_column("Expressiveness", justify="right", style="yellow")

            for i, (chunk, label) in enumerate(zip(chunks, detected_labels)):
                snippet = chunk[:40] + ("..." if len(chunk) > 40 else "")
                expr_val = map_emotion_label(label)
                table.add_row(str(i + 1), snippet, label.upper(), f"{expr_val:.2f}")

            state.console.print(table)

            preview_action = questionary.select(
                "Review detected emotions:",
                choices=[
                    questionary.Choice(title="✔ Continue with synthesis", value="continue"),
                    questionary.Choice(title="Override with Calm style", value="override_calm"),
                    questionary.Choice(title="Override with Normal style", value="override_normal"),
                    questionary.Choice(title="Override with Expressive style", value="override_expressive"),
                    questionary.Choice(title="← Cancel job", value="cancel"),
                ],
                default="continue",
            ).ask()

            if preview_action == "cancel" or not preview_action:
                return "menu"
            elif preview_action == "override_calm":
                emotion_choice = "calm"
            elif preview_action == "override_normal":
                emotion_choice = "normal"
            elif preview_action == "override_expressive":
                emotion_choice = "expressive"

        except Exception as e:
            logger.warning("Emotion preview failed, proceeding with default auto: %s", e)

    # S-24: Output mode selection
    output_choice = questionary.select(
        "Select output destination (S-24):",
        choices=[
            questionary.Choice(title="Save to audio file (.wav)", value="save"),
            questionary.Choice(title="Play through speaker", value="play"),
            questionary.Choice(title="Both (Save and Play)", value="both"),
        ],
        default="save",
    ).ask()

    if not output_choice:
        output_choice = "save"

    # S-25: Execution and progress streaming
    job_service = JobService(
        conn=state.conn,
        config=state.config,
        model_manager=state.model_manager,
    )

    try:
        job = job_service.create_text_job(
            profile_id=selected_profile.id,
            input_text=input_text,
            emotion_mode=emotion_choice,
            output_mode=output_choice,
        )

        render_panel(
            state.console,
            title=f"Starting Speech Synthesis (Job: {job.id[:8]})",
            lines=[
                f"Speaker Profile : {selected_profile.name}",
                f"Emotion Style   : {emotion_choice.capitalize()}",
                f"Output Mode     : {output_choice.capitalize()}",
                f"Characters      : {len(input_text)}",
            ],
            kind="info",
            plain=plain,
        )

        last_result = None
        for event in job_service.run_job(job.id):
            if event.stage == "split":
                state.console.print(f"[bold cyan]• Text Split:[/bold cyan] {event.message}")
            elif event.stage == "emotion":
                state.console.print(f"[bold magenta]• Emotion Analysis:[/bold magenta] {event.message}")
            elif event.stage == "preparing":
                state.console.print(f"[dim]• Preparing:[/dim] {event.message}")
            elif event.stage == "loading_model":
                state.console.print(f"[bold yellow]• Model Manager:[/bold yellow] {event.message}")
            elif event.stage == "synthesizing":
                idx = (event.chunk_index or 0) + 1
                tot = event.total_chunks or 1
                state.console.print(f"[green]• Synthesizing [{idx}/{tot}]:[/green] {event.message}")
            elif event.stage == "joining":
                state.console.print(f"[dim]• DSP Join:[/dim] {event.message}")
            elif event.stage == "done":
                last_result = event.result
                state.console.print("[bold green]✔ Synthesis completed successfully![/bold green]")
            elif event.stage in ("failed", "cancelled"):
                state.console.print(f"[bold red]✖ {event.stage.upper()}:[/bold red] {event.message}")

        # S-26: Result Panel
        if last_result and last_result.output_path:
            render_panel(
                state.console,
                title="Synthesis Result (S-26)",
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

            # Post-generation actions
            while True:
                action = questionary.select(
                    "Result options:",
                    choices=[
                        questionary.Choice(title="Replay generated audio", value="replay"),
                        questionary.Choice(title="Synthesize another text", value="again"),
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
                    return "text_to_voice"
                else:
                    break

    except VoxcloneError as err:
        render_panel(
            state.console,
            title=f"Synthesis Error: {err.error_code}",
            lines=[str(err), f"Hint: {err.hint}" if hasattr(err, "hint") else ""],
            kind="error",
            plain=plain,
        )
    except Exception as err:
        logger.error("Unexpected error in text-to-voice screen: %s", err, exc_info=True)
        render_panel(
            state.console,
            title="System Error",
            lines=[str(err)],
            kind="error",
            plain=plain,
        )

    return "menu"
