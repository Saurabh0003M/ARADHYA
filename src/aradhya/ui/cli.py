"""Rich CLI rendering for the Aradhya assistant.

Every user-facing print now goes through this module so the terminal
experience is consistent, modern, and beautiful.  Import the shared
``console`` object anywhere you need output.
"""

from __future__ import annotations

import io
import os
import sys
from dataclasses import dataclass
from typing import Any, Iterator

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
from rich.live import Live
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
    table.add_row("/topology", "Show detected local device topology")
    table.add_row("/topology rescan", "Regenerate topology for this machine")
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
    table.add_row("/model workers", "List local and optional cloud model workers")
    table.add_row("/model workers assess <text>", "Check if text is safe for cloud routing")
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

    # API catalog
    table.add_row("[heading]-- Public APIs --", "")
    table.add_row("/apis", "Show API catalog source and categories")
    table.add_row("/apis search <query>", "Search the local public API catalog")
    table.add_row("/apis category <name>", "List APIs in a category")
    table.add_row("/apis inspect <name>", "Show one API entry and risk label")
    table.add_row("/apis recommend <need>", "Recommend APIs for a stated need")

    # Federation
    table.add_row("[heading]-- Federation --", "")
    table.add_row("/federation init", "Create local LAN federation identity")
    table.add_row("/federation status", "Show local federation status")
    table.add_row("/federation doctor", "Run federation foundation diagnostics")

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
    model_status = "[success]Ready[/]" if model_ok else (
        "[error]Not ready[/]" if model_ok is False else "[dim]Unknown[/]"
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


def render_topology(topology: dict[str, Any], *, path: str, refreshed: bool = False) -> None:
    """Render the local topology manifest."""

    title = "Topology"
    if refreshed:
        title += " (rescanned)"
    table = Table(
        title=f"[heading]{title}[/]",
        box=box.ROUNDED,
        border_style="dim",
        show_header=False,
        expand=False,
    )
    table.add_column("", style="accent", no_wrap=True)
    table.add_column("")
    table.add_row("Path", f"[dim]{path}[/]")
    table.add_row("Mode", str(topology.get("transport", {}).get("mode", "unknown")))
    table.add_row("Local node", str(topology.get("local_node_id", "unknown")))

    nodes = topology.get("nodes") or []
    table.add_row("Nodes", str(len(nodes)))
    for node in nodes:
        resources = node.get("resources", {})
        caps = node.get("capabilities", [])
        table.add_row(
            str(node.get("node_id", "unknown")),
            (
                f"{node.get('role', 'unknown')} / {node.get('device_class', 'unknown')} | "
                f"CPU {resources.get('cpu_count', '?')} | "
                f"RAM {resources.get('ram_gb', 'unknown')} GB | "
                f"{len(caps)} capabilities"
            ),
        )
    console.print(table)
    console.print()


def render_federation_status(status: dict[str, Any]) -> None:
    """Render federation identity and peer status."""

    identity = status.get("identity", {})
    table = Table(
        title="[heading]Federation Status[/]",
        box=box.ROUNDED,
        border_style="dim",
        show_header=False,
        expand=False,
    )
    table.add_column("", style="accent", no_wrap=True)
    table.add_column("")
    table.add_row("Mode", str(status.get("mode", "unknown")))
    table.add_row("Transport", "active" if status.get("transport_active") else "not started")
    table.add_row("Node", str(identity.get("node_id", "unknown")))
    table.add_row("Fingerprint", str(identity.get("fingerprint", "unknown")))
    table.add_row("Peers", str(status.get("peer_count", 0)))
    table.add_row("State", f"[dim]{status.get('state_dir', '')}[/]")
    console.print(table)
    console.print()


def render_federation_doctor(checks: list[dict[str, Any]]) -> None:
    """Render federation diagnostics."""

    table = Table(
        title="[heading]Federation Doctor[/]",
        box=box.ROUNDED,
        border_style="dim",
        show_header=True,
        expand=False,
    )
    table.add_column("Check", style="accent", no_wrap=True)
    table.add_column("Status", no_wrap=True)
    table.add_column("Detail")
    for check in checks:
        ok = bool(check.get("ok"))
        table.add_row(
            str(check.get("name", "?")),
            "[success]OK[/]" if ok else "[error]FAIL[/]",
            str(check.get("detail", "")),
        )
    console.print(table)
    console.print()


# ── Voice status ──────────────────────────────────────────────────────

def render_model_workers(statuses: list[Any]) -> None:
    """Render local and optional cloud model workers."""

    table = Table(
        title="[heading]Model Workers[/]",
        box=box.ROUNDED,
        border_style="dim",
        show_header=True,
        expand=False,
    )
    table.add_column("Worker", style="accent", no_wrap=True)
    table.add_column("Role", no_wrap=True)
    table.add_column("Owner", no_wrap=True)
    table.add_column("Provider", no_wrap=True)
    table.add_column("Model")
    table.add_column("Privacy", no_wrap=True)
    table.add_column("Status", no_wrap=True)

    for status in statuses:
        worker = status.worker
        state = str(status.status)
        if state in {"configured", "local"}:
            rendered_status = f"[success]{state}[/]"
        elif state == "disabled":
            rendered_status = "[dim]disabled[/]"
        else:
            rendered_status = f"[warning]{state}[/]"
        table.add_row(
            worker.worker_id,
            worker.role,
            worker.owner,
            worker.provider,
            worker.model_name,
            worker.privacy_mode,
            rendered_status,
        )

    console.print(table)
    for status in statuses:
        if status.status not in {"configured", "local"}:
            console.print(f"  [dim]{status.worker.worker_id}: {status.detail}[/]")
    console.print()


def render_cloud_safety_assessment(assessment: Any) -> None:
    """Render cloud privacy gate results."""

    style = "success" if assessment.allowed else "error"
    table = Table(
        title="[heading]Cloud Privacy Gate[/]",
        box=box.ROUNDED,
        border_style="dim",
        show_header=False,
        expand=False,
    )
    table.add_column("", style="accent", no_wrap=True)
    table.add_column("")
    table.add_row("Allowed", f"[{style}]{assessment.allowed}[/]")
    table.add_row("Risk", str(assessment.risk_level))
    table.add_row("Summary", str(assessment.summary))
    console.print(table)

    if assessment.findings:
        findings = Table(
            box=box.SIMPLE,
            border_style="dim",
            show_header=True,
            expand=False,
        )
        findings.add_column("Severity", no_wrap=True)
        findings.add_column("Code", no_wrap=True)
        findings.add_column("Message")
        for finding in assessment.findings:
            findings.add_row(finding.severity, finding.code, finding.message)
        console.print(findings)
    console.print()


def render_api_categories(source: Any, categories: list[tuple[str, int]]) -> None:
    """Render public API catalog category counts."""

    table = Table(
        title="[heading]Public API Catalog[/]",
        box=box.ROUNDED,
        border_style="dim",
        show_header=False,
        expand=False,
    )
    table.add_column("", style="accent", no_wrap=True)
    table.add_column("")
    table.add_row("Source", str(source.kind))
    table.add_row("Entries", str(source.entry_count))
    table.add_row("Repo", str(source.url))
    if source.path is not None:
        table.add_row("Cache", str(source.path))
    console.print(table)

    cat_table = Table(
        box=box.SIMPLE,
        border_style="dim",
        show_header=True,
        expand=False,
    )
    cat_table.add_column("Category", style="accent")
    cat_table.add_column("Count", justify="right")
    for category, count in categories:
        cat_table.add_row(category, str(count))
    console.print(cat_table)
    console.print()


def render_api_entries(title: str, entries: list[Any], risk_labels: dict[str, str]) -> None:
    """Render API search/recommend/category results."""

    if not entries:
        render_info("No matching API entries in the local catalog.")
        return

    table = Table(
        title=f"[heading]{title}[/]",
        box=box.ROUNDED,
        border_style="dim",
        show_header=True,
        expand=False,
    )
    table.add_column("API", style="accent", no_wrap=True)
    table.add_column("Category", no_wrap=True)
    table.add_column("Auth", no_wrap=True)
    table.add_column("HTTPS", no_wrap=True)
    table.add_column("Risk")
    table.add_column("Description")
    for entry in entries:
        table.add_row(
            entry.name,
            entry.category,
            entry.auth,
            "yes" if entry.https else "no",
            risk_labels.get(entry.name, "unknown"),
            entry.description,
        )
    console.print(table)
    console.print()


def render_api_entry(entry: Any, risk_label: str) -> None:
    """Render one API catalog entry."""

    table = Table(
        title=f"[heading]API: {entry.name}[/]",
        box=box.ROUNDED,
        border_style="dim",
        show_header=False,
        expand=False,
    )
    table.add_column("", style="accent", no_wrap=True)
    table.add_column("")
    table.add_row("Category", entry.category)
    table.add_row("Auth", entry.auth)
    table.add_row("HTTPS", "yes" if entry.https else "no")
    table.add_row("CORS", entry.cors)
    table.add_row("Risk", risk_label)
    table.add_row("Link", entry.link or "[dim]unknown[/]")
    table.add_row("Description", entry.description)
    table.add_row("Rule", "External calls still require an explicit confirmed action.")
    console.print(table)
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
    routing_pattern = re.compile(r"\[Routed to (.+?) \u2014 (.+?)\]\n*")
    for match in routing_pattern.finditer(remaining):
        model_name = match.group(1)
        reason = match.group(2)
        console.print(
            f"  [dim]\u27f3 Routed \u2192 [accent]{model_name}[/accent] ({reason})[/]"
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
        for thought in thoughts:
            cleaned = thought.strip()
            if cleaned:
                if len(cleaned) > 200:
                    cleaned = cleaned[:200] + "\u2026"
                console.print(f"  [dim italic]\U0001f4ad {cleaned}[/]")
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
        console.print(Markdown(body, code_theme="monokai"), width=100)
    else:
        console.print(f"{prefix}{body}")

    console.print()
