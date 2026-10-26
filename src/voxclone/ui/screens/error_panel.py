"""Standardized Error Panel screen (S-57) with dynamic recovery actions."""

from typing import Any

import questionary

from voxclone.errors import VoxcloneError
from voxclone.ui.components import render_error
from voxclone.ui.theme import questionary_style


def show_error_panel(
    state: Any,
    err: VoxcloneError,
    job_id: str | None = None,
) -> str | None:
    """Render the standard error screen S-57 and prompt user with recovery options.

    Args:
        state: Active SessionState.
        err: The VoxcloneError instance that occurred.
        job_id: Optional ID of the job associated with the failure.

    Returns:
        The action key executed, or None if user chose 'Back'.
    """
    console = state.console
    render_error(console, err, debug=state.debug, theme=state.theme)

    # Check if job is resumable
    job = None
    if job_id and hasattr(state, "job_service"):
        try:
            job = state.job_service.get_job(job_id)
        except Exception:
            job = None

    is_resumable = bool(job and job.is_resumable)

    # Build action options
    # Map: label -> action_key
    actions: list[tuple[str, str]] = []

    if is_resumable and "resume" in err.recovery_actions:
        actions.append(("Resume job", "resume"))

    if "free_gpu" in err.recovery_actions:
        label = "Free GPU memory then resume" if is_resumable else "Free GPU memory"
        actions.append((label, "free_gpu"))

    if "doctor" in err.recovery_actions:
        actions.append(("Open Doctor", "doctor"))

    if "fetch_models" in err.recovery_actions:
        actions.append(("Show how to download models", "fetch_models"))

    if "log_path" in err.recovery_actions:
        actions.append(("Show log file path", "log_path"))

    back_label = "<- Back" if state.plain else "← Back"
    actions.append((back_label, "back"))

    # Prompt user
    chosen_key = "back"
    if state.plain:
        console.print("\nAvailable Recovery Actions:")
        for idx, (label, _) in enumerate(actions, start=1):
            console.print(f"  {idx}. {label}")
        try:
            raw_input = input(f"Select action [1-{len(actions)}]: ").strip()
            sel_idx = int(raw_input) - 1
            if 0 <= sel_idx < len(actions):
                chosen_key = actions[sel_idx][1]
        except Exception:
            chosen_key = "back"
    else:
        choices = [label for label, _ in actions]
        try:
            sel_label = questionary.select(
                "What would you like to do?",
                choices=choices,
                style=questionary_style(state.theme),
            ).ask()
            for label, key in actions:
                if label == sel_label:
                    chosen_key = key
                    break
        except KeyboardInterrupt:
            chosen_key = "back"

    # Execute selected action
    if chosen_key == "resume" and job_id:
        from voxclone.ui.screens.job_history import screen_resume_job

        screen_resume_job(state, job_id)
        return "resume"

    elif chosen_key == "free_gpu":
        try:
            res = state.model_service.free_gpu_memory()
            freed_mb = res.get("freed_mb", 0)
            console.print(f"[green]GPU memory freed (+{freed_mb} MB).[/green]")
        except Exception as exc:
            console.print(f"[yellow]Failed to free GPU memory: {exc!s}[/yellow]")

        if is_resumable and job_id:
            from voxclone.ui.screens.job_history import screen_resume_job

            screen_resume_job(state, job_id)
        return "free_gpu"

    elif chosen_key == "doctor":
        from voxclone.ui.screens.system import screen_doctor

        screen_doctor(state)
        return "doctor"

    elif chosen_key == "fetch_models":
        console.print("\n[bold cyan]Model Download Instructions:[/bold cyan]")
        console.print("To pull required neural voice model weights to your local system, run:")
        console.print("  [bold]voxclone system fetch-models[/bold]\n")
        if state.plain:
            input("Press Enter to continue...")
        else:
            questionary.press_any_key_to_continue().ask()
        return "fetch_models"

    elif chosen_key == "log_path":
        log_file = state.config.logs_dir / "voxclone.log"
        console.print(f"\n[cyan]Log file location:[/cyan] [bold]{log_file.resolve()}[/bold]\n")
        if state.plain:
            input("Press Enter to continue...")
        else:
            questionary.press_any_key_to_continue().ask()
        return "log_path"

    return None
