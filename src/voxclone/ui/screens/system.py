"""System management screens: Model status, Doctor diagnostics, and Storage reporting."""

from typing import Any

import questionary

from voxclone.services.system_service import get_storage_report, run_doctor
from voxclone.ui.components import render_header, render_panel, render_table
from voxclone.ui.menu import select
from voxclone.ui.theme import badge


def screen_model_status(state: Any) -> None:
    """Display current neural model residency and GPU memory usage (S-51 stub)."""
    model_name = "No model is loaded"
    vram_detail = "unknown"

    if hasattr(state, "model_manager") and state.model_manager is not None:
        if state.model_manager.resident_model_key:
            model_name = f"Resident model: {state.model_manager.resident_model_key}"
        free_mb = state.model_manager.get_free_vram_mb()
        if free_mb is not None:
            vram_detail = f"{free_mb} MB ({round(free_mb / 1024, 2)} GB)"

    render_panel(
        console=state.console,
        title="Model Status (S-51)",
        lines=[
            f"Active Model: {model_name}",
            f"Free VRAM:    {vram_detail}",
            "",
            "Models are loaded dynamically on demand and unloaded after processing.",
        ],
        kind="info",
        plain=state.plain,
    )
    if not state.plain:
        questionary.press_any_key_to_continue("Press any key to return...").ask()


def screen_doctor(state: Any) -> None:
    """Execute host and container pre-flight diagnostics and render results (S-53)."""
    checks = run_doctor(state.config)

    columns = ["Check", "Status", "Detail", "Fix Hint"]
    rows: list[list[str]] = []

    for chk in checks:
        icon, word, _ = badge("success" if chk.ok else "error", theme=state.theme)
        status_text = f"{icon} {word}"
        rows.append([chk.name, status_text, chk.detail, chk.fix_hint or "-"])

    render_table(
        console=state.console,
        title="System Doctor Diagnostics (S-53)",
        columns=columns,
        rows=rows,
        plain=state.plain,
    )
    if not state.plain:
        questionary.press_any_key_to_continue("Press any key to return...").ask()


def screen_storage(state: Any) -> None:
    """Display disk space consumption across VoxClone data directories (S-56)."""
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
        title="Storage Utilization Report (S-56)",
        columns=columns,
        rows=rows,
        plain=state.plain,
    )
    if not state.plain:
        questionary.press_any_key_to_continue("Press any key to return...").ask()


def screen_system_menu(state: Any) -> None:
    """Render the System admin dropdown menu (S-50)."""
    choices = [
        "Model status",
        "Doctor (system checks)",
        "Storage",
        "Settings",
    ]

    while True:
        state.console.clear() if not state.plain else None
        render_header(state.console, state)

        choice = select(
            state=state,
            message="System Menu",
            choices=choices,
            allow_back=True,
        )

        if choice is None:
            break

        if choice == "Model status":
            screen_model_status(state)
        elif choice == "Doctor (system checks)":
            screen_doctor(state)
        elif choice == "Storage":
            screen_storage(state)
        elif choice == "Settings":
            render_panel(
                state.console,
                title="Settings Configuration",
                lines=[
                    "Interactive Settings editor arrives in Milestone P5.",
                    "Use environment variables or SQLite app_settings to modify settings.",
                ],
                kind="warning",
                plain=state.plain,
            )
            if not state.plain:
                questionary.press_any_key_to_continue("Press any key to return...").ask()
