"""Welcome, Help, and About screens (S-02, S-03, S-04)."""

import questionary
from rich.table import Table

from voxclone import __version__
from voxclone.constants import APP_NAME
from voxclone.ui.components import render_header, render_panel
from voxclone.ui.session import SessionState


def screen_welcome(state: SessionState) -> None:
    """Render the first-run welcome and onboarding screen (S-02)."""
    state.console.clear()
    render_header(state.console, state)

    lines = [
        f"[bold cyan]Welcome to {APP_NAME} v{__version__}[/bold cyan]",
        "",
        "VoxClone is a production-grade, privacy-first local voice cloning CLI application.",
        "Synthesize natural speech from text or convert voice recordings using a zero-shot",
        "reference audio sample — 100% offline with zero telemetry.",
        "",
        "[bold yellow]Core Ethical Principles:[/bold yellow]",
        "  • Explicit consent is mandatory for every enrolled voice profile (VX-103).",
        "  • All audio processing and neural inference execute strictly on your local machine.",
        "  • Voice reference samples are never transmitted across the network.",
        "",
        "[bold green]Quick Start Steps:[/bold green]",
        "  1. [bold]Voice Profiles:[/bold] Enroll a voice by recording 15-30s or importing a WAV/MP3 file.",
        "  2. [bold]Speak to Voice (VC):[/bold] Convert input microphone speech or an audio recording.",
        "  3. [bold]Text to Voice (TTS):[/bold] Type text and synthesize speech matching your target profile.",
        "  4. [bold]Outputs:[/bold] Listen to, inspect, or manage converted audio artifacts.",
        "  5. [bold]System:[/bold] Run diagnostics ('doctor'), check VRAM, or tune performance settings.",
    ]
    render_panel(state.console, "Welcome & Overview", lines, kind="info", plain=state.plain)

    if not state.plain:
        questionary.text("Press Enter to continue to the main menu...", qmark="→").ask()
    else:
        input("Press Enter to continue to the main menu...")


def screen_help(state: SessionState) -> None:
    """Render the navigation, CLI options, and error code reference screen (S-03)."""
    state.console.clear()
    render_header(state.console, state)

    nav_lines = [
        "[bold cyan]Keyboard Navigation:[/bold cyan]",
        "  • [bold]Up / Down Arrows (k / j):[/bold] Navigate menu choices",
        "  • [bold]Enter:[/bold] Confirm selection or execute action",
        "  • [bold]Esc / q:[/bold] Go back to previous screen or cancel input",
        "  • [bold]Ctrl + C:[/bold] Cancel current generation job or exit immediately",
        "",
        "[bold cyan]Common CLI Flags:[/bold cyan]",
        "  • [bold]--plain:[/bold] Disable rich ANSI menus and interactive prompts (suitable for scripts)",
        "  • [bold]--debug:[/bold] Enable verbose logging and full traceback output",
        "  • [bold]--device <cuda|cpu|auto>:[/bold] Override compute hardware acceleration",
        "  • [bold]--no-color:[/bold] Strip terminal color codes for monospaced logs",
    ]
    render_panel(state.console, "Help & Navigation", nav_lines, kind="info", plain=state.plain)

    if not state.plain:
        table = Table(title="VoxClone Error Code Index", box=None, show_header=True)
        table.add_column("Code", style="bold red", width=10)
        table.add_column("Category", style="cyan", width=18)
        table.add_column("Description", style="white")
        table.add_row("VX-101", "Sample Quality", "Speech duration under 10.0 seconds")
        table.add_row("VX-102", "Sample Format", "Unsupported audio container or codec")
        table.add_row("VX-103", "Consent Required", "Voice cloning consent prompt was declined")
        table.add_row("VX-201", "Text Input", "Empty or invalid text provided for synthesis")
        table.add_row("VX-210", "Speech Presence", "No speech detected in audio recording (pure silence)")
        table.add_row("VX-300", "VRAM Budget", "Insufficient GPU VRAM to load requested neural model")
        table.add_row("VX-301", "CUDA OOM", "Out of memory during audio chunk inference")
        table.add_row("VX-302", "GPU Missing", "CUDA explicitly requested but no NVIDIA GPU detected")
        table.add_row("VX-310", "Model Missing", "Required AI model weights not found on disk")
        table.add_row("VX-401", "Microphone", "Default audio input device unavailable or in use")
        table.add_row("VX-402", "Speaker", "Default audio playback device unavailable")
        table.add_row("VX-500", "Job Interrupted", "Processing aborted by user signal or crash recovery")
        state.console.print(table)
        questionary.text("Press Enter to return...", qmark="→").ask()
    else:
        state.console.print("Error Codes: VX-101..VX-103 (Input), VX-201..VX-210 (Text), VX-300..VX-310 (GPU), VX-401..VX-402 (Audio), VX-500 (Jobs)")
        input("Press Enter to return...")


def screen_about(state: SessionState) -> None:
    """Render application version, credits, and architecture notes (S-04)."""
    state.console.clear()
    render_header(state.console, state)

    lines = [
        f"[bold cyan]{APP_NAME} v{__version__}[/bold cyan]",
        "Local Zero-Shot Voice Cloning System",
        "",
        "[bold]Hardware Envelope & vGPU Optimization:[/bold]",
        "  • Single-resident model architecture (only 1 AI model in VRAM at any time).",
        "  • Tuned for 8 GB vGPU execution with 6000 MB VRAM safety ceiling.",
        "  • Dynamic 3.0s - 5.0s silence-aware audio chunking for low memory footprint.",
        "",
        "[bold]Integrated Neural Engines:[/bold]",
        "  • [bold]TTS Engine:[/bold] F5-TTS / E2-TTS Zero-Shot Diffusion Transformer (~3.5 GB VRAM)",
        "  • [bold]VC Engine:[/bold] OpenVoice V2 Zero-Shot Tone Color Converter (~2.2 GB VRAM)",
        "  • [bold]Emotion Engine:[/bold] DistilRoBERTa Multi-Class Emotion Classifier (~0.6 GB VRAM)",
        "",
        "[bold]Data Storage:[/bold]",
        f"  • SQLite database: [dim]{state.config.db_path}[/dim]",
        f"  • Voice profiles: [dim]{state.config.profiles_dir}[/dim]",
        f"  • Output audio: [dim]{state.config.outputs_dir}[/dim]",
        "",
        "License: Apache-2.0 / Open Research",
    ]
    render_panel(state.console, "About VoxClone", lines, kind="info", plain=state.plain)

    if not state.plain:
        questionary.text("Press Enter to return...", qmark="→").ask()
    else:
        input("Press Enter to return...")
