"""Rich CLI rendering for the Aradhya assistant.

Every user-facing print now goes through this module so the terminal
experience is consistent, modern, and beautiful.  Import the shared
``console`` object anywhere you need output.
"""

from __future__ import annotations

import io
import os
import sys
from typing import Any

# Force UTF-8 on Windows terminals before Rich initializes.
if sys.platform == "win32":
    os.system("")  # enables ANSI escape codes on Windows 10+
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            sys.stdout = io.TextIOWrapper(
                sys.stdout.buffer, encoding="utf-8", errors="replace",
            )

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.theme import Theme
from rich.columns import Columns
from rich.markdown import Markdown
from rich import box

# ── Global theme ──────────────────────────────────────────────────────
ARADHYA_THEME = Theme(
    {
        "aradhya": "bold #00d4aa",
        "user": "bold #61afef",
        "heading": "bold #c678dd",
        "success": "bold #98c379",
        "warning": "bold #e5c07b",
        "error": "bold #e06c75",
        "dim": "dim #7f848e",
        "accent": "#56b6c2",
        "highlight": "bold #d19a66",
    }
)

console = Console(theme=ARADHYA_THEME, highlight=False)


# ── Startup banner ────────────────────────────────────────────────────
def render_banner(model_name: str, voice_inbox: str, skills_active: int,
                  skills_total: int, log_path: str) -> None:
    """Print the beautiful startup banner with key system info."""

    banner_text = (
        "    _    ____      _    ____  _   ___   __ _\n"
        "   / \\  |  _ \\    / \\  |  _ \\| | | \\ \\ / // \\\n"
        "  / _ \\ | |_) |  / _ \\ | | | | |_| |\\ V // _ \\\n"
        " / ___ \\|  _ <  / ___ \\| |_| |  _  | | |/ ___ \\\n"
        "/_/   \\_\\_| \\_\\/_/   \\_\\____/|_| |_| |_/_/   \\_\\\n"
    )

    console.print(
        Panel(
            f"[bold #00d4aa]{banner_text}[/]\n"
            "[dim]       Operating Intelligence  v1.0[/]",
            border_style="#00d4aa",
            padding=(0, 4),
        )
    )
    console.print()

    # System info table
    info = Table(box=box.SIMPLE, border_style="dim", show_header=False,
                 pad_edge=False, expand=False)
    info.add_column("Key", style="accent", no_wrap=True)
    info.add_column("Value")
    info.add_row("  Model", f"[highlight]{model_name}[/]")
    info.add_row("  Voice", f"{voice_inbox}")
    info.add_row("  Skills", f"{skills_active} active / {skills_total} loaded")
    info.add_row("  Log", f"[dim]{log_path}[/]")
    console.print(info)
    console.print()
    console.print(
        "[dim]  Type [accent]/help[/accent] for commands  |  "
        "Just type naturally to talk to Aradhya[/]"
    )
    console.print()


# ── Response rendering ────────────────────────────────────────────────
def render_response(spoken: str, transcript_echo: str | None = None,
                    awaiting: bool = False) -> None:
    """Render an Aradhya response with optional transcript echo."""
    if transcript_echo:
        console.print(f"  [dim]Heard >[/] {transcript_echo}")

    style = "aradhya"
    prefix = "  [aradhya]Aradhya >[/] "

    if awaiting:
        console.print(
            Panel(
                f"{spoken}\n\n[dim]Say [accent]yes proceed[/accent] to execute, "
                "or [accent]cancel[/accent] to discard.[/]",
                title="[~] Awaiting Confirmation",
                border_style="warning",
                padding=(0, 2),
            )
        )
    else:
        console.print(f"{prefix}{spoken}")
    console.print()


# ── Help command ──────────────────────────────────────────────────────
def render_help() -> None:
    """Show categorized command reference."""
    table = Table(
        title="[heading]Aradhya Commands[/]",
        box=box.ROUNDED,
        border_style="dim",
        title_style="heading",
        show_lines=True,
        expand=False,
    )
    table.add_column("Command", style="accent", no_wrap=True, min_width=22)
    table.add_column("Description")

    # Core
    table.add_row("[heading]── Core ──", "")
    table.add_row("/help", "Show this command reference")
    table.add_row("/status", "Show system status (model, voice, skills, state)")
    table.add_row("/sleep", "Send Aradhya to idle")
    table.add_row("exit", "Shut down Aradhya")

    # Voice
    table.add_row("[heading]── Voice ──", "")
    table.add_row("/voice", "Show voice pipeline status")
    table.add_row("/voice process", "Process pending audio files from inbox")
    table.add_row("/voice activate", "Start live microphone capture")
    table.add_row("/voice stop", "Stop live microphone capture")
    table.add_row("/wake-word on", "Start continuous wake word detection")
    table.add_row("/wake-word off", "Stop wake word detection")

    # Model
    table.add_row("[heading]── Model ──", "")
    table.add_row("/model", "Check configured model health")
    table.add_row("/model ask <prompt>", "Send a direct prompt to the local model")

    # Skills
    table.add_row("[heading]-- Skills --", "")
    table.add_row("/skills", "List all loaded skills with status")
    table.add_row("/skills enable <name>", "Enable a skill")
    table.add_row("/skills disable <name>", "Disable a skill")

    # Tools
    table.add_row("[heading]-- Tools --", "")
    table.add_row("/icon on", "Launch the floating quick-access icon")
    table.add_row("/icon off", "Close the floating icon")
    table.add_row("/cache", "Rebuild and benchmark the context cache")

    # Telegram
    table.add_row("[heading]-- Telegram --", "")
    table.add_row("/telegram start", "Start Telegram bot for remote access")
    table.add_row("/telegram stop", "Stop Telegram bot")

    # Safety
    table.add_row("[heading]-- Safety --", "")
    table.add_row("/audit", "Show recent audit log entries")

    # Daemon
    table.add_row("[heading]-- Daemon --", "")
    table.add_row("/daemon start", "Start background daemon (survives terminal close)")
    table.add_row("/daemon stop", "Stop background daemon")

    # Setup
    table.add_row("[heading]-- Setup --", "")
    table.add_row("/setup", "Run the interactive setup wizard")

    console.print(table)
    console.print()
    console.print(
        "[dim]  Tip: Or just type naturally -- Aradhya understands plain English.[/]"
    )
    console.print()


# ── Status command ────────────────────────────────────────────────────
def render_status(
    *,
    is_awake: bool,
    model_name: str,
    model_ok: bool | None,
    pending_plan: Any,
    voice_provider: str,
    voice_running: bool,
    skills_active: int,
    skills_total: int,
    live_execution: bool,
) -> None:
    """Render a compact status dashboard."""
    table = Table(
        title="[heading]System Status[/]",
        box=box.ROUNDED,
        border_style="dim",
        show_header=False,
        expand=False,
    )
    table.add_column("", style="accent", no_wrap=True)
    table.add_column("")

    state_icon = "[+]" if is_awake else "[~]"
    state_text = "[success]Awake[/]" if is_awake else "[warning]Idle[/]"
    table.add_row(f"{state_icon} State", state_text)

    model_icon = "[+]" if model_ok else ("[!]" if model_ok is False else "[?]")
    model_status = "[success]Connected[/]" if model_ok else (
        "[error]Offline[/]" if model_ok is False else "[dim]Unknown[/]"
    )
    table.add_row(f"{model_icon} Model", f"{model_name} — {model_status}")

    plan_text = (
        f"[warning]{pending_plan.kind.value}[/] awaiting confirmation"
        if pending_plan else "[dim]None[/]"
    )
    table.add_row("Pending Plan", plan_text)

    voice_icon = "[+]" if voice_running else "[ ]"
    voice_text = f"{voice_provider}" + (
        " — [success]listening[/]" if voice_running else ""
    )
    table.add_row(f"{voice_icon} Voice", voice_text)

    table.add_row("Skills", f"{skills_active} active / {skills_total} loaded")

    exec_icon = "[+]" if live_execution else "[x]"
    exec_text = "[success]Enabled[/]" if live_execution else "[warning]Dry-run[/]"
    table.add_row(f"{exec_icon} Execution", exec_text)

    console.print(table)
    console.print()


# ── Voice status ──────────────────────────────────────────────────────
def render_voice_status(status: Any, activation_support: Any,
                        runtime_profile: Any,
                        voice_running: bool) -> None:
    """Render detailed voice pipeline status."""
    table = Table(
        title="[heading]Voice Pipeline[/]",
        box=box.ROUNDED,
        border_style="dim",
        show_header=False,
        expand=False,
    )
    table.add_column("", style="accent", no_wrap=True, min_width=24)
    table.add_column("")

    table.add_row("Provider", f"[highlight]{status.provider}[/]")
    table.add_row("Inbox", str(status.inbox_dir))
    table.add_row("Processed", str(status.processed_dir))
    table.add_row("Transcripts", str(status.transcripts_dir))
    table.add_row("Manual Transcripts", str(status.manual_transcripts_dir))
    table.add_row("Supported Audio", ", ".join(status.supported_extensions))

    if status.provider == "faster_whisper":
        table.add_row("Whisper Model", status.faster_whisper_model_size)
        table.add_row("Whisper Device", status.faster_whisper_device)
        table.add_row("Whisper Compute", status.faster_whisper_compute_type)
        table.add_row("Language", status.language or "auto")

    live_icon = "[+]" if voice_running else "[ ]"
    table.add_row(
        f"{live_icon} Live Activation",
        "[success]Running[/]" if voice_running else "[dim]Stopped[/]",
    )
    table.add_row("Available", "Yes" if activation_support.available else "No")
    table.add_row("Note", activation_support.message)
    table.add_row(
        "Spoken Replies",
        "[success]Enabled[/]" if runtime_profile.voice_output.enabled else "[dim]Disabled[/]",
    )

    pending = status.pending_audio
    table.add_row(
        "Pending Audio",
        f"[warning]{len(pending)} file(s)[/]" if pending else "[dim]None[/]",
    )

    console.print(table)

    if pending:
        for p in pending:
            console.print(f"  [dim]  - {p.name}[/]")

    console.print()


# ── Skills list ───────────────────────────────────────────────────────
def render_skills_list(skills: list[Any]) -> None:
    """Render skill list as a rich table."""
    if not skills:
        console.print("  [dim]No skills loaded.[/]")
        console.print()
        return

    table = Table(
        title=f"[heading]Skills ({len(skills)})[/]",
        box=box.ROUNDED,
        border_style="dim",
        expand=False,
    )
    table.add_column("Status", justify="center", width=8)
    table.add_column("Name", style="accent")
    table.add_column("Description")

    for skill in skills:
        icon = "[success]ON[/]" if skill.enabled else "[dim]OFF[/]"
        table.add_row(icon, skill.name, skill.description)

    console.print(table)
    console.print()


# ── Health check ──────────────────────────────────────────────────────
def render_health_check(checks: list[tuple[str, bool, str]]) -> None:
    """Render startup health check results.

    Each check is (name, passed, message).
    """
    console.print("[heading]  Health Check[/]")
    all_ok = True
    for name, passed, message in checks:
        icon = "[success][+][/]" if passed else "[error][!][/]"
        if not passed:
            all_ok = False
        console.print(f"  {icon} {name}: {message}")

    if all_ok:
        console.print("  [success]All systems ready.[/]")
    else:
        console.print(
            "\n  [warning]Some checks failed. Run [accent]/help[/accent] "
            "or fix the issues above.[/]"
        )
    console.print()


# ── Misc ──────────────────────────────────────────────────────────────
def render_info(message: str) -> None:
    console.print(f"  [dim]>[/] {message}")

def render_success(message: str) -> None:
    console.print(f"  [success][+][/] {message}")

def render_warning(message: str) -> None:
    console.print(f"  [warning][~][/] {message}")

def render_error(message: str) -> None:
    console.print(f"  [error][!][/] {message}")

def get_prompt() -> str:
    """Return styled user prompt text for input()."""
    return "[user]You >[/user] "

def prompt_input() -> str:
    """Read user input with a styled prompt."""
    return console.input(get_prompt())
