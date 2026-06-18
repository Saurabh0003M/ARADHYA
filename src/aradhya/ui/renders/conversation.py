"""Interactive / conversational renderers: responses, help, voice status, the
tool-confirmation prompt, user input, and live streaming.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator

from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.live import Live
from rich import box
from rich.markup import escape

from src.aradhya.ui.console import console


# ── Response rendering ────────────────────────────────────────────────
def render_response(spoken: str, transcript_echo: str | None = None,
                    awaiting: bool = False) -> None:
    """Render an Aradhya response with optional transcript echo."""
    if transcript_echo:
        console.print(f"  [dim]Heard >[/] {transcript_echo}")

    if not spoken and not awaiting:
        console.print()
        return

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
def render_help(topic: str | None = None) -> None:
    """Show categorized command reference."""
    categories = {
        "Core": [
            ("/help [topic]", "Show this command reference (or specific topic)"),
            ("/status", "Show system status (model, voice, skills, state)"),
            ("/topology", "Show detected local device topology"),
            ("/topology rescan", "Regenerate topology for this machine"),
            ("/sleep", "Send Aradhya to idle"),
            ("exit", "Shut down Aradhya"),
        ],
        "Voice": [
            ("/voice", "Show voice pipeline status"),
            ("/voice process", "Process pending audio files from inbox"),
            ("/voice activate", "Start live microphone capture"),
            ("/voice stop", "Stop live microphone capture"),
            ("/wake-word on", "Start continuous wake word detection"),
            ("/wake-word off", "Stop wake word detection"),
        ],
        "Model": [
            ("/model", "Check configured model health"),
            ("/model workers", "List local and optional cloud model workers"),
            ("/model workers assess <text>", "Check if text is safe for cloud routing"),
            ("/model ask <prompt>", "Send a direct prompt to the local model"),
        ],
        "Skills": [
            ("/skills", "List all loaded skills with status"),
            ("/skills enable <name>", "Enable a skill"),
            ("/skills disable <name>", "Disable a skill"),
        ],
        "Tools": [
            ("/icon on", "Launch the floating quick-access icon"),
            ("/icon off", "Close the floating icon"),
            ("/cache", "Rebuild and benchmark the context cache"),
        ],
        "APIs": [
            ("/apis", "Show API catalog source and categories"),
            ("/apis search <query>", "Search the local public API catalog"),
            ("/apis category <name>", "List APIs in a category"),
            ("/apis inspect <name>", "Show one API entry and risk label"),
            ("/apis recommend <need>", "Recommend APIs for a stated need"),
        ],
        "Parasite": [
            ("/parasite status", "Show host repo digestion status"),
            ("/parasite candidates", "Rank digested host repos for integration"),
            ("/parasite inspect <repo>", "Inspect one host integration candidate"),
            ("/parasite ledger", "Write the host integration ledger JSON"),
        ],
        "Federation": [
            ("/federation init", "Create local LAN federation identity"),
            ("/federation status", "Show local federation status"),
            ("/federation doctor", "Run federation foundation diagnostics"),
        ],
        "Telegram": [
            ("/telegram start", "Start Telegram bot for remote access"),
            ("/telegram stop", "Stop Telegram bot"),
        ],
        "Safety": [
            ("/audit", "Show recent audit log entries"),
        ],
        "Daemon": [
            ("/daemon start", "Start background daemon"),
            ("/daemon stop", "Stop background daemon"),
        ],
        "Setup": [
            ("/setup", "Run the interactive setup wizard"),
        ]
    }

    if topic:
        topic_normalized = topic.strip().lower()
        matched_cat = next((k for k in categories.keys() if k.lower() == topic_normalized), None)
        if not matched_cat:
            console.print(f"  [error]Unknown help topic '{topic}'.[/]")
            console.print(f"  [dim]Available topics: {', '.join(categories.keys())}[/]")
            console.print()
            return

        table = Table(
            title=f"[heading]Aradhya Commands: {matched_cat}[/]",
            box=box.ROUNDED,
            border_style="dim",
            title_style="heading",
            expand=False,
        )
        table.add_column("Command", style="accent", no_wrap=True, min_width=22)
        table.add_column("Description")
        for cmd, desc in categories[matched_cat]:
            table.add_row(cmd, desc)
        console.print(table)
    else:
        # Show all topics in grouped tables, but compactly
        for cat_name, commands in categories.items():
            table = Table(
                title=f"[heading]-- {cat_name} --[/]",
                box=box.SIMPLE,
                border_style="dim",
                title_style="heading",
                expand=False,
                show_header=False,
                pad_edge=False,
            )
            table.add_column("Command", style="accent", no_wrap=True, min_width=26)
            table.add_column("Description")
            for cmd, desc in commands:
                table.add_row(f"  {cmd}", desc)
            console.print(table)

    console.print()
    console.print(
        "[dim]  Tip: Type `/help <topic>` to view a specific category. "
        "Or just type naturally![/]"
    )
    console.print()


@dataclass
class VoiceStatusConfig:
    status: Any
    activation_support: Any
    runtime_profile: Any
    voice_running: bool


def render_voice_status(config: VoiceStatusConfig) -> None:
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

    table.add_row("Provider", f"[highlight]{config.status.provider}[/]")
    table.add_row("Inbox", str(config.status.inbox_dir))
    table.add_row("Processed", str(config.status.processed_dir))
    table.add_row("Transcripts", str(config.status.transcripts_dir))
    table.add_row("Manual Transcripts", str(config.status.manual_transcripts_dir))
    table.add_row("Supported Audio", ", ".join(config.status.supported_extensions))

    if config.status.provider == "faster_whisper":
        table.add_row("Whisper Model", config.status.faster_whisper_model_size)
        table.add_row("Whisper Device", config.status.faster_whisper_device)
        table.add_row("Whisper Compute", config.status.faster_whisper_compute_type)
        table.add_row("Language", config.status.language or "auto")

    live_icon = "[+]" if config.voice_running else "[ ]"
    table.add_row(
        f"{live_icon} Live Activation",
        "[success]Running[/]" if config.voice_running else "[dim]Stopped[/]",
    )
    table.add_row("Available", "Yes" if config.activation_support.available else "No")
    table.add_row("Note", config.activation_support.message)
    table.add_row(
        "Spoken Replies",
        "[success]Enabled[/]" if config.runtime_profile.voice_output.enabled else "[dim]Disabled[/]",
    )

    pending = config.status.pending_audio
    table.add_row(
        "Pending Audio",
        f"[warning]{len(pending)} file(s)[/]" if pending else "[dim]None[/]",
    )

    console.print(table)

    if pending:
        for p in pending:
            console.print(f"  [dim]  - {p.name}[/]")

    console.print()


def render_tool_confirmation_prompt(tool_name: str, arguments: dict[str, Any]) -> None:
    """Render a detailed security confirmation panel for a dangerous tool."""

    # Extract common dangerous arguments
    command = escape(str(arguments.get("command", "")))
    path = escape(str(arguments.get("path", "")))
    cwd = escape(str(arguments.get("cwd", "")))
    url = escape(str(arguments.get("url", "")))

    details = Table(box=box.SIMPLE, show_header=False, pad_edge=False, expand=False)
    details.add_column("Key", style="accent")
    details.add_column("Value")

    details.add_row("Tool", f"[bold]{escape(tool_name)}[/]")
    if command:
        details.add_row("Command", f"[highlight]{command}[/]")
    if path:
        details.add_row("Path", path)
    if cwd:
        details.add_row("CWD", cwd)
    if url:
        details.add_row("URL", url)

    # Any other arguments not handled above
    for k, v in arguments.items():
        if k not in ("command", "path", "cwd", "url"):
            val_str = str(v)
            if len(val_str) > 100:
                val_str = val_str[:100] + "..."
            details.add_row(escape(k.capitalize()), escape(val_str))

    # Risk level heuristics
    risk_level = "High"
    border_style = "error"
    if tool_name in ("browser_click", "browser_type"):
        risk_level = "Medium"
        border_style = "warning"
    elif tool_name in ("write_file", "delete_file", "move_file", "run_command", "open_url"):
        risk_level = "Critical"
        border_style = "error"

    details.add_row("Risk", f"[{border_style}]{risk_level}[/]")

    panel = Panel(
        details,
        title="[!] Security Gate",
        border_style=border_style,
        padding=(0, 2),
    )
    console.print(panel)
    console.print(r"  Approve? [success]\[y]es[/] / [success]\[a]lways[/] / [error]\[n]o[/]")


def get_prompt() -> str:
    """Return styled user prompt text for input()."""
    return "[user]You >[/user] "


def prompt_input() -> str:
    """Read user input with a styled prompt."""
    return console.input(get_prompt())


def render_stream(stream: Iterator[str], prefix: str = "  [aradhya]Aradhya >[/] ", style: str = "") -> str:
    """Render a live stream of text chunks with post-processing.

    During streaming: raw text shown live for instant feedback.
    After streaming: re-rendered with thought/routing/markdown formatting.
    Returns the complete text after the stream finishes.
    """
    full_text = ""
    text_renderable = Text.from_markup(prefix)

    with Live(text_renderable, console=console, refresh_per_second=15, transient=True) as live:
        for chunk in stream:
            full_text += chunk
            if style:
                text_renderable.append(chunk, style=style)
            else:
                text_renderable.append(chunk)
            live.update(text_renderable)

    # Post-process: render with proper formatting
    _render_formatted_response(full_text, prefix)
    return full_text


def _render_formatted_response(text: str, prefix: str = "  [aradhya]Aradhya >[/] ") -> None:
    """Post-process and render a model response with proper formatting.

    Splits routing notices, thinking blocks, and the main body into
    separate Rich-styled sections.
    """
    import re
    from rich.markdown import Markdown

    remaining = text

    # 1. Extract and render routing notices
    routing_pattern = re.compile(r"\[Routed to (.+?) - (.+?)\]\n*")
    for match in routing_pattern.finditer(remaining):
        model_name = match.group(1)
        reason = match.group(2)
        console.print(
            f"  [dim][~] Routed -> [accent]{model_name}[/accent] ({reason})[/]"
        )
    remaining = routing_pattern.sub("", remaining)

    # 2. Extract and render <thought>/<think> blocks
    think_pattern = re.compile(
        r"<(?:thought|think)>(.*?)</(?:thought|think)>",
        re.DOTALL,
    )
    thoughts = think_pattern.findall(remaining)
    remaining = think_pattern.sub("", remaining)

    if thoughts:
        console.print("  [dim italic][~] <thought> (hidden for brevity)[/]")
        console.print()

    # 3. Render the main body
    body = remaining.strip()
    if not body:
        return

    has_markdown = any(
        marker in body
        for marker in ("## ", "```", "| ", "- **", "1. ", "* ", "---")
    )

    if has_markdown:
        console.print(prefix.rstrip())
        # Cap markdown width to 100 or console width, whichever is smaller, to fit narrow terminals
        render_width = min(console.width, 100) if console.width else 100
        console.print(Markdown(body, code_theme="monokai"), width=render_width)
    else:
        console.print(f"{prefix}{body}")

    console.print()
