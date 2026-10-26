"""Job history and resume interactive screens (S-40 to S-43)."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import questionary
from rich.table import Table

from voxclone.audio.io import load_audio, play_audio
from voxclone.errors import VoxcloneError
from voxclone.services.job_service import JobService
from voxclone.storage import chunks_repo
from voxclone.ui.components import render_header, render_panel
from voxclone.ui.session import SessionState

logger = logging.getLogger("voxclone.ui.job_history")


def screen_job_history(state: SessionState) -> str:
    """Execute Job History interactive screen stack (S-40 to S-43)."""
    job_service = JobService(
        conn=state.conn,
        config=state.config,
        model_manager=state.model_manager,
    )
    plain = state.plain

    while True:
        state.console.clear() if not plain else None
        render_header(state.console, state)

        jobs = job_service.list_recent_jobs(limit=30)
        if not jobs:
            render_panel(
                state.console,
                title="Job History (S-40)",
                lines=[
                    "No speech synthesis or voice conversion jobs have been executed yet.",
                    "",
                    "Generate speech via 'Text → my voice' or 'Recording → my voice'",
                    "to see execution records and resume points here.",
                ],
                kind="info",
                plain=plain,
            )
            if not plain:
                questionary.text("Press Enter to return to main menu...", qmark="→").ask()
            else:
                input("Press Enter to return...")
            return "menu"

        # S-40: Render Jobs Table
        table = Table(title="Recent Generation Jobs (S-40)", expand=False)
        table.add_column("ID", style="cyan", width=10)
        table.add_column("Type", style="bold", width=14)
        table.add_column("Profile", width=14)
        table.add_column("Status", width=12)
        table.add_column("Chunks", justify="right", width=8)
        table.add_column("Audio", justify="right", width=10)
        table.add_column("Elapsed / RTF", justify="right", width=14)
        table.add_column("Created", style="dim", width=16)

        for j in jobs:
            status_style = "bold green" if j.status == "succeeded" else (
                "bold red" if j.status == "failed" else (
                    "bold yellow" if j.status == "cancelled" else "bold cyan"
                )
            )
            type_label = "Text → Voice" if j.job_type == "text_to_voice" else "Conversion"
            chunks_str = f"{j.completed_chunks}/{j.total_chunks}"
            audio_str = f"{j.output_duration_sec:.1f} s" if j.output_duration_sec else "-"
            rtf_str = f"{j.real_time_factor:.2f}x" if j.real_time_factor else "-"
            created_str = j.created_at[:16].replace("T", " ") if j.created_at else "-"

            table.add_row(
                j.id[:8],
                type_label,
                j.profile_name_snapshot,
                f"[{status_style}]{j.status}[/{status_style}]",
                chunks_str,
                audio_str,
                rtf_str,
                created_str,
            )

        state.console.print(table)

        # Build interactive choice list
        job_choices = [
            questionary.Choice(
                title=f"{j.id[:8]} | {j.job_type[:10]} | {j.profile_name_snapshot} | {j.status}",
                value=j.id,
            )
            for j in jobs
        ]
        job_choices.append(questionary.Choice(title="← Return to main menu", value="back"))

        selected_job_id = questionary.select(
            "Select job to inspect, resume, replay, or delete:",
            choices=job_choices,
        ).ask()

        if not selected_job_id or selected_job_id == "back":
            return "menu"

        selected_job = job_service.get_job(selected_job_id)
        if not selected_job:
            continue

        # Sub-menu for selected job
        while True:
            actions = [
                questionary.Choice(title="View job details (S-41)", value="details"),
            ]
            if selected_job.status in ("failed", "cancelled", "running", "queued"):
                actions.append(questionary.Choice(title="Resume job from checkpoint (S-42)", value="resume"))
            if selected_job.output_path and Path(selected_job.output_path).is_file():
                actions.append(questionary.Choice(title="Replay generated audio", value="replay"))
            actions.append(questionary.Choice(title="Delete job record (S-43)", value="delete"))
            actions.append(questionary.Choice(title="← Back to job list", value="back"))

            action = questionary.select(
                f"Actions for Job {selected_job.id[:8]}:",
                choices=actions,
            ).ask()

            if not action or action == "back":
                break

            if action == "details":
                # S-41: Job Details View
                chunks = chunks_repo.list_chunks(state.conn, selected_job.id)
                lines = [
                    f"Job ID          : {selected_job.id}",
                    f"Job Type        : {selected_job.job_type}",
                    f"Profile Name    : {selected_job.profile_name_snapshot}",
                    f"Current Status  : {selected_job.status.upper()}",
                    f"Total Chunks    : {selected_job.total_chunks} (completed: {selected_job.completed_chunks})",
                    f"Created At      : {selected_job.created_at}",
                    f"Finished At     : {selected_job.finished_at or '-'}",
                    f"Elapsed Time    : {selected_job.elapsed_ms / 1000.0:.2f} s" if selected_job.elapsed_ms else "Elapsed Time    : -",
                    f"RTF Multiplier  : {selected_job.real_time_factor:.2f}x" if selected_job.real_time_factor else "RTF Multiplier  : -",
                    f"Output File     : {selected_job.output_path or '(none)'}",
                ]
                if selected_job.error_message:
                    lines.append(f"Error Message   : {selected_job.error_message} ({selected_job.error_code or 'VX-900'})")

                render_panel(
                    state.console,
                    title=f"Job Details: {selected_job.id[:8]} (S-41)",
                    lines=lines,
                    kind="info",
                    plain=plain,
                )

                if chunks:
                    chunk_table = Table(title="Chunk Pipeline Records", expand=False)
                    chunk_table.add_column("#", justify="right")
                    chunk_table.add_column("Kind")
                    chunk_table.add_column("Status")
                    chunk_table.add_column("Time / Length")
                    chunk_table.add_column("Output File")
                    for c in chunks:
                        time_info = f"{c.start_sec:.1f}s - {c.end_sec:.1f}s" if c.start_sec is not None else "-"
                        out_info = Path(c.output_path).name if c.output_path else "-"
                        chunk_table.add_row(str(c.chunk_index + 1), c.kind, c.status, time_info, out_info)
                    state.console.print(chunk_table)

                if not plain:
                    questionary.text("Press Enter to continue...", qmark="→").ask()
                else:
                    input("Press Enter to continue...")

            elif action == "replay":
                try:
                    state.console.print("[cyan]Playing generated audio...[/cyan]")
                    audio, sr = load_audio(selected_job.output_path)
                    play_audio(audio, sr)
                except Exception as exc:
                    state.console.print(f"[yellow]Audio playback failed: {exc}[/yellow]")

            elif action == "resume":
                # S-42: Resume Job Execution
                state.console.print(f"[bold cyan]Resuming job {selected_job.id[:8]} from last checkpoint...[/bold cyan]")
                last_result = None
                for event in job_service.resume_job(selected_job.id):
                    state.console.print(f"• [{event.stage}] {event.message}")
                    if event.stage == "done":
                        last_result = event.result

                if last_result and last_result.output_path:
                    render_panel(
                        state.console,
                        title="Resume Succeeded (S-26/S-35)",
                        lines=[
                            f"Output Path : {last_result.output_path}",
                            f"Duration    : {last_result.duration_sec:.2f} s",
                            f"Time Elapsed: {last_result.elapsed_ms / 1000.0:.2f} s",
                            f"Speed (RTF) : {last_result.real_time_factor:.2f}x",
                        ],
                        kind="success",
                        plain=plain,
                    )
                # Refresh selected job model
                selected_job = job_service.get_job(selected_job.id) or selected_job

            elif action == "delete":
                # S-43: Delete Job Confirmation
                if questionary.confirm(f"Are you sure you want to delete job {selected_job.id[:8]}?", default=False).ask():
                    del_file = False
                    if selected_job.output_path and Path(selected_job.output_path).is_file():
                        del_file = questionary.confirm("Also delete generated output WAV file from disk?", default=False).ask()
                    job_service.delete_job(selected_job.id, delete_output=del_file)
                    state.console.print("[green]✔ Job record deleted successfully.[/green]")
                    break
