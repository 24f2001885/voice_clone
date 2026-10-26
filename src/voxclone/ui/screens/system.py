"""System management screens: Model status, Free GPU, Doctor, and Storage (S-50 to S-56)."""

import time
from typing import Any

import questionary
from rich.table import Table

from voxclone.services.system_service import (
    fetch_models,
    get_storage_report,
    run_doctor,
)
from voxclone.ui.components import render_header, render_panel, render_table
from voxclone.ui.menu import select
from voxclone.ui.theme import badge


def screen_model_status(state: Any) -> None:
    """Display current neural model residency and GPU memory usage (S-51)."""
    state.console.clear() if not state.plain else None
    render_header(state.console, state)

    status = state.model_service.get_status() if hasattr(state, "model_service") and state.model_service else None

    if status is None:
        resident = "No model manager active"
        device = "unknown"
        vram_info = "n/a"
    else:
        resident = status.resident_key or "(none — memory clean)"
        device = status.device
        if status.vram_free_mb is not None and status.vram_total_mb is not None:
            vram_info = f"{status.vram_free_mb} MB free / {status.vram_total_mb} MB total ({status.vram_used_mb} MB used)"
        else:
            vram_info = "CPU execution mode (VRAM not tracked)"

    lines = [
        f"[bold cyan]Active Resident Model :[/bold cyan] [bold]{resident}[/bold]",
        f"[bold cyan]Target Compute Device :[/bold cyan] {device}",
        f"[bold cyan]Hardware VRAM Status  :[/bold cyan] {vram_info}",
        f"[bold cyan]Keep-Warm Retention   :[/bold cyan] {'Enabled (resident until switch)' if getattr(status, 'keep_warm', True) else 'Disabled (unload per job)'}",
        f"[bold cyan]Execution Mode        :[/bold cyan] {getattr(status, 'engine_mode', 'standard')}",
        "",
        "[dim]Rule: Strictly <= 1 neural model resides in VRAM to prevent memory collisions.[/dim]",
    ]
    render_panel(state.console, "Neural Model & Hardware Status (S-51)", lines, kind="info", plain=state.plain)

    # Render recent model lifecycle events table
    if hasattr(state, "model_service") and state.model_service:
        events = state.model_service.get_recent_events(limit=8)
        if events:
            if state.plain:
                state.console.print("\n--- Recent Model Lifecycle Events ---")
                for ev in events:
                    dur = f"{ev.duration_ms}ms" if ev.duration_ms is not None else "-"
                    vram_delta = f"{ev.vram_free_before_mb}->{ev.vram_free_after_mb}MB" if ev.vram_free_before_mb is not None else "-"
                    state.console.print(f"  {ev.created_at[:19]} | {ev.action:<6} | {ev.model_key:<7} | {dur:<7} | {vram_delta}")
            else:
                table = Table(title="Recent Model Lifecycle Events", box=None, show_header=True)
                table.add_column("Timestamp", style="dim", width=20)
                table.add_column("Action", style="bold", width=10)
                table.add_column("Model", style="cyan", width=10)
                table.add_column("Device", width=8)
                table.add_column("Duration", style="green", width=10)
                table.add_column("VRAM Delta", style="dim", width=18)

                for ev in events:
                    action_style = "bold green" if ev.action == "load" else ("bold yellow" if ev.action == "unload" else "bold red")
                    dur_str = f"{ev.duration_ms} ms" if ev.duration_ms is not None else "-"
                    vram_str = f"{ev.vram_free_before_mb} -> {ev.vram_free_after_mb} MB" if ev.vram_free_before_mb is not None else "-"
                    table.add_row(
                        ev.created_at[:19].replace("T", " "),
                        f"[{action_style}]{ev.action}[/{action_style}]",
                        ev.model_key,
                        ev.device,
                        dur_str,
                        vram_str,
                    )
                state.console.print(table)

    if not state.plain:
        questionary.text("Press Enter to return...", qmark="→").ask()
    else:
        input("\nPress Enter to return...")


def screen_free_gpu(state: Any) -> None:
    """Manually unload any resident model and clear PyTorch CUDA caches (S-52)."""
    state.console.clear() if not state.plain else None
    render_header(state.console, state)

    if not hasattr(state, "model_service") or not state.model_service:
        render_panel(state.console, "Model Service Unavailable", ["Model service is not loaded."], kind="error", plain=state.plain)
        if not state.plain:
            questionary.text("Press Enter to return...", qmark="→").ask()
        return

    with state.console.status("[cyan]Unloading resident models and purging CUDA caches...[/cyan]"):
        res = state.model_service.free_gpu_memory()

    unloaded = res.get("unloaded_key") or "(no model was resident)"
    freed_mb = res.get("freed_mb")
    free_now_mb = res.get("free_now_mb")

    lines = [
        f"Unloaded Model : [bold]{unloaded}[/bold]",
        f"Compute Device : {res.get('device', 'unknown')}",
    ]
    if freed_mb is not None:
        lines.append(f"Reclaimed VRAM : [bold green]+{freed_mb} MB[/bold green]")
    if free_now_mb is not None:
        lines.append(f"Available Free : [bold cyan]{free_now_mb} MB[/bold cyan]")
    lines.extend([
        "",
        "Garbage collection executed and CUDA tensor cache evacuated.",
    ])

    render_panel(state.console, "GPU Memory Evacuation Complete (S-52)", lines, kind="success", plain=state.plain)
    if not state.plain:
        questionary.text("Press Enter to continue...", qmark="→").ask()
    else:
        input("Press Enter to continue...")


def screen_fetch_models(state: Any) -> None:
    """Download or verify local presence of neural model weights."""
    state.console.clear() if not state.plain else None
    render_header(state.console, state)

    state.console.print("[cyan]Verifying model weights for TTS, VC, and Emotion engines...[/cyan]")
    results = fetch_models(state.config)

    columns = ["Model Key", "Repository", "Status", "Detail"]
    rows = []
    for r in results:
        status_str = "[bold green]READY[/bold green]" if r.ok else "[bold red]FAILED[/bold red]"
        rows.append([r.model_key, r.repo_id, status_str, r.detail])

    render_table(
        console=state.console,
        title="Neural Weights Cache Verification",
        columns=columns,
        rows=rows,
        plain=state.plain,
    )
    if not state.plain:
        questionary.text("Press Enter to return...", qmark="→").ask()
    else:
        input("Press Enter to return...")


def screen_doctor(state: Any) -> None:
    """Execute host and container pre-flight diagnostics and render results (S-53)."""
    state.console.clear() if not state.plain else None
    render_header(state.console, state)

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
        questionary.text("Press Enter to return...", qmark="→").ask()
    else:
        input("Press Enter to return...")


def screen_storage(state: Any) -> None:
    """Display disk space consumption across VoxClone data directories (S-56)."""
    state.console.clear() if not state.plain else None
    render_header(state.console, state)

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
        questionary.text("Press Enter to return...", qmark="→").ask()
    else:
        input("Press Enter to return...")


def screen_settings_overview(state: Any) -> None:
    """Render interactive Settings configuration editor (S-54 & S-55)."""
    from voxclone.services.settings_service import SettingsService

    settings_svc = SettingsService(conn=state.conn, config=state.config)
    plain = state.plain

    while True:
        state.console.clear() if not plain else None
        render_header(state.console, state)

        all_settings = settings_svc.get_all()

        table = Table(title="Application Settings (S-54)", expand=False)
        table.add_column("Setting Key", style="cyan", width=22)
        table.add_column("Current Value", style="bold", width=20)
        table.add_column("Source", width=10)
        table.add_column("Status", width=12)

        for key, s_val in all_settings.items():
            status_text = "[bold yellow]LOCKED (env)[/bold yellow]" if s_val.locked else "[green]Modifiable[/green]"
            table.add_row(key, str(s_val.value), s_val.source, status_text)

        state.console.print(table)

        choices = [
            questionary.Choice(
                title=f"{k}: {s.value} {'(LOCKED)' if s.locked else ''}",
                value=k,
            )
            for k, s in all_settings.items()
        ]
        choices.append(questionary.Choice(title="↺ Reset all non-locked settings to defaults", value="reset"))
        choices.append(questionary.Choice(title="← Back to System menu", value="back"))

        picked_key = questionary.select(
            "Select setting to edit (S-55):",
            choices=choices,
        ).ask()

        if not picked_key or picked_key == "back":
            break

        if picked_key == "reset":
            if questionary.confirm("Reset all non-locked database settings to default values?", default=False).ask():
                settings_svc.reset_defaults()
                state.console.print("[green]✔ Settings reset to defaults.[/green]")
                time.sleep(0.5)
            continue

        selected_setting = all_settings[picked_key]
        if selected_setting.locked:
            render_panel(
                state.console,
                title=f"Setting '{picked_key}' is Locked",
                lines=[
                    f"This setting is locked by environment variable override: {selected_setting.value}",
                    "To modify it, edit or remove it from your .env file and restart the application.",
                ],
                kind="warning",
                plain=plain,
            )
            if not plain:
                questionary.text("Press Enter to continue...", qmark="→").ask()
            else:
                input("Press Enter to continue...")
            continue

        # Edit prompt (S-55)
        new_val_str = questionary.text(
            f"Enter new value for '{picked_key}' (current: {selected_setting.value}):",
            default=str(selected_setting.value),
        ).ask()

        if new_val_str is not None and new_val_str != str(selected_setting.value):
            try:
                settings_svc.set(picked_key, new_val_str)
                state.console.print(f"[bold green]✔ Successfully updated '{picked_key}'![/bold green]")
                time.sleep(0.6)
            except Exception as exc:
                render_panel(
                    state.console,
                    title="Setting Validation Error",
                    lines=[str(exc)],
                    kind="error",
                    plain=plain,
                )
                if not plain:
                    questionary.text("Press Enter to continue...", qmark="→").ask()
                else:
                    input("Press Enter to continue...")


def screen_system_menu(state: Any) -> None:
    """Render the System admin dropdown menu (S-50)."""
    choices = [
        "Model status (S-51)",
        "Free GPU memory (S-52)",
        "Verify / Fetch model weights",
        "Doctor (system checks) (S-53)",
        "Storage utilization (S-56)",
        "Settings (S-54 & S-55)",
        "Remote Colab GPU worker (S-58)",
    ]

    while True:
        state.console.clear() if not state.plain else None
        render_header(state.console, state)

        choice = select(
            state=state,
            message="System Menu (S-50)",
            choices=choices,
            allow_back=True,
        )

        if choice is None:
            break

        if choice == "Model status (S-51)":
            screen_model_status(state)
        elif choice == "Free GPU memory (S-52)":
            screen_free_gpu(state)
        elif choice == "Verify / Fetch model weights":
            screen_fetch_models(state)
        elif choice == "Doctor (system checks) (S-53)":
            screen_doctor(state)
        elif choice == "Storage utilization (S-56)":
            screen_storage(state)
        elif choice == "Settings (S-54 & S-55)":
            screen_settings_overview(state)
        elif choice == "Remote Colab GPU worker (S-58)":
            from voxclone.ui.screens.remote_worker import screen_remote_worker

            screen_remote_worker(state)

