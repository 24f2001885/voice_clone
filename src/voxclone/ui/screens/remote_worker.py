"""Remote Colab GPU Worker Status & Setup Screen (S-58)."""

from pathlib import Path
import time
from typing import Any

import questionary
from rich.table import Table

from voxclone.transport.drive_queue import (
    check_worker_heartbeat,
    get_queue_stats,
    write_heartbeat,
)
from voxclone.ui.components import render_header, render_panel
from voxclone.ui.theme import questionary_style


def screen_remote_worker(state: Any) -> None:
    """Render screen S-58 showing Google Drive Colab worker status, queue depths, and setup."""
    console = state.console
    drive_dir: Path = getattr(state.config, "drive_dir", Path("drive_queue"))

    while True:
        console.clear() if not state.plain else None
        render_header(console, state)

        # 1. Fetch Worker Status
        worker_info = None
        status_text = "OFFLINE"
        status_color = "red"
        detail_lines = []

        try:
            worker_info = check_worker_heartbeat(drive_dir, max_age_sec=180.0)
            status_text = "ONLINE (Active)"
            status_color = "green"
            gpu = worker_info.get("gpu_name", "NVIDIA GPU")
            vram_used = worker_info.get("vram_used_mb", 0)
            vram_tot = worker_info.get("vram_total_mb", 0)
            age = worker_info.get("heartbeat_age_sec", 0)
            detail_lines.append(f"GPU Hardware : {gpu}")
            detail_lines.append(f"Worker State : {worker_info.get('status', 'idle')}")
            detail_lines.append(f"VRAM Usage   : {vram_used} MB / {vram_tot} MB")
            detail_lines.append(f"Last Ping    : {age:.0f}s ago")
        except Exception as exc:
            status_text = "OFFLINE"
            status_color = "red"
            detail_lines.append(f"Status Note  : {exc!s}")

        # 2. Queue statistics
        stats = get_queue_stats(drive_dir)

        # 3. Render Status Table
        table = Table(title="Google Drive Remote GPU Worker (S-58)", expand=False)
        table.add_column("Property", style="cyan")
        table.add_column("Value", style="bold")

        table.add_row("Execution Mode", getattr(state.config, "backend", "local").upper())
        table.add_row("Drive Queue Path", str(drive_dir.resolve()))
        table.add_row("Worker Status", f"[{status_color}]{status_text}[/{status_color}]")
        for line in detail_lines:
            k, _, v = line.partition(":")
            table.add_row(k.strip(), v.strip())
        table.add_row("Inbox Tasks", str(stats.get("inbox_count", 0)))
        table.add_row("Outbox Results", str(stats.get("outbox_count", 0)))

        console.print(table)
        console.print()

        # 4. Action Choices
        back_label = "<- Back" if state.plain else "← Back"
        actions = [
            "Refresh status",
            "Send test queue ping",
            "Show Colab setup guide",
            back_label,
        ]

        if state.plain:
            console.print("Available Actions:")
            for idx, act in enumerate(actions, start=1):
                console.print(f"  {idx}. {act}")
            choice = input(f"Select choice [1-{len(actions)}]: ").strip()
            if choice == "1":
                continue
            elif choice == "2":
                _ping_test(state, drive_dir)
            elif choice == "3":
                _show_colab_guide(state)
            else:
                break
        else:
            sel = questionary.select(
                "Select action:",
                choices=actions,
                style=questionary_style(state.theme),
            ).ask()

            if sel == "Refresh status":
                continue
            elif sel == "Send test queue ping":
                _ping_test(state, drive_dir)
            elif sel == "Show Colab setup guide":
                _show_colab_guide(state)
            else:
                break


def _ping_test(state: Any, drive_dir: Path) -> None:
    """Simulate or verify local queue write."""
    console = state.console
    console.print("\n[cyan]Sending queue probe ping...[/cyan]")
    try:
        drive_dir.mkdir(parents=True, exist_ok=True)
        probe_file = drive_dir / "heartbeat" / "probe.tmp"
        probe_file.write_text(f"probe_{time.time()}", encoding="utf-8")
        probe_file.unlink()
        console.print("[green]✔ Local Google Drive queue directory is writable![/green]")
    except Exception as exc:
        console.print(f"[red]✖ Queue write probe failed: {exc!s}[/red]")

    if not state.plain:
        questionary.press_any_key_to_continue().ask()
    else:
        input("Press Enter to continue...")


def _show_colab_guide(state: Any) -> None:
    """Display step-by-step instructions for launching Colab GPU worker."""
    console = state.console
    lines = [
        "How to use free Google Colab NVIDIA T4 GPU with VoxClone:",
        "",
        "1. Open https://colab.research.google.com and sign into your Google account.",
        "2. Upload 'scripts/colab_worker.ipynb' from this project repository.",
        "3. In the Colab menu: Runtime > Change runtime type > Select 'T4 GPU'.",
        "4. Run Cell 1 to mount Google Drive ('/content/drive/MyDrive/VoxClone_Queue').",
        "5. Run Cell 2 to install dependencies, then Cell 3 to begin the polling loop.",
        "6. In your local VoxClone project, set VOXCLONE_BACKEND=remote_drive in .env.",
        "7. Run 'voxclone speak' or 'voxclone convert' - tasks will process on the free GPU!",
    ]
    render_panel(console, title="Google Colab Setup Guide", lines=lines, kind="info", plain=state.plain)
    if not state.plain:
        questionary.press_any_key_to_continue().ask()
    else:
        input("Press Enter to continue...")
