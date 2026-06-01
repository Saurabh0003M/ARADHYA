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
from rich.markup import escape

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
            "[dim]       Operating Intelligence  v1.1[/]",
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


# ── Status command ────────────────────────────────────────────────────
def render_status(
    *,
    is_awake: bool,
    model_provider_name: str,
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

    # 1. State
    state_icon = "[+]" if is_awake else "[~]"
    state_text = "[success]Awake[/]" if is_awake else "[warning]Idle[/]"
    table.add_row(f"{state_icon} State", state_text)

    # 2. Safety / Execution
    exec_icon = "[!]" if live_execution else "[~]"
    exec_text = "[error]Live Execution Enabled[/]" if live_execution else "[success]Dry-run Mode[/]"
    table.add_row(f"{exec_icon} Safety", exec_text)

    # 3. Pending Plan
    if pending_plan:
        plan_text = f"[warning]{pending_plan.kind.value}[/] awaiting confirmation"
        table.add_row("[!] Action", plan_text)
    else:
        table.add_row("[ ] Action", "[dim]None pending[/]")

    # 4. Model Health
    model_icon = "[+]" if model_ok else ("[!]" if model_ok is False else "[?]")
    model_status = "[success]Ready[/]" if model_ok else (
        "[error]Not ready[/]" if model_ok is False else "[dim]Unknown[/]"
    )
    table.add_row(f"{model_icon} Model", f"{model_name} - {model_status}")

    # 5. Privacy / Cloud Fallback
    cloud_icon = "[!]" if model_provider_name != "ollama" else "[+]"
    cloud_text = (
        "[warning]Cloud API (Privacy Gate Active)[/]"
        if model_provider_name != "ollama"
        else "[success]Local Inference Only[/]"
    )
    table.add_row(f"{cloud_icon} Privacy", cloud_text)

    # 6. Voice
    voice_icon = "[+]" if voice_running else "[ ]"
    voice_text = f"{voice_provider}" + (
        " - [success]listening[/]" if voice_running else ""
    )
    table.add_row(f"{voice_icon} Voice", voice_text)

    # 7. Skills
    table.add_row("[~] Skills", f"{skills_active} active / {skills_total} loaded")

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


def render_audit(entries: list[dict[str, Any]], last_session: str, tool_ok: int, tool_fail: int, security_count: int) -> None:
    """Render recent audit log events."""
    console.print()
    console.print("[heading]  Audit Log - Last 20 Events[/]")
    console.print(
        f"  Tools: [success]{tool_ok} OK[/]  [error]{tool_fail} FAIL[/]  "
        f"|  Security events: [warning]{security_count}[/]  "
        f"|  Session: [dim]{last_session[:12]}[/]"
    )
    console.print()

    for entry in entries:
        raw_ts = entry.get("ts", "")
        if raw_ts and "T" in raw_ts:
            ts = raw_ts[5:19].replace("T", " ")   # "MM-DD HH:MM:SS"
        else:
            ts = raw_ts[-8:] if raw_ts else "??:??:??"
        etype = entry.get("type", "?")

        if etype == "tool_call":
            tool = entry.get("tool", "?")
            ok = entry.get("success", False)
            status_tag = "[success]OK  [/]" if ok else "[error]FAIL[/]"
            preview = (entry.get("output_preview", "") or "")[:60]
            console.print(
                f"  [dim]{ts}[/] {status_tag} [accent]{tool:<22}[/]"
                + (f" [dim]{preview}[/]" if preview else "")
            )
        elif etype == "turn_start":
            msg = (entry.get("user_message", "") or "")[:50]
            console.print(f"  [dim]{ts}[/] [accent]> TURN[/]  [dim]{msg}[/]")
        elif etype == "turn_end":
            iters = entry.get("iterations", "?")
            calls = entry.get("tool_calls_count", 0)
            ok = entry.get("success", True)
            status_tag = "[success]OK[/]" if ok else "[error]X[/]"
            console.print(
                f"  [dim]{ts}[/] {status_tag} [accent]END[/]    "
                f"[dim]iter={iters} tools={calls}[/]"
            )
        elif etype == "command":
            cmd = entry.get("command", "?")
            console.print(f"  [dim]{ts}[/] [accent]CMD[/]    {cmd}")
        elif etype in ("security", "tool_blocked_dry_run"):
            evt = entry.get("event", entry.get("message", "?"))
            console.print(f"  [dim]{ts}[/] [warning]! SEC[/]  {evt}")
        else:
            console.print(f"  [dim]{ts}[/] [dim]{etype}[/]")

    console.print()
    console.print(
        "  [dim]Showing 20 of latest events. "
        "Full log: ~/.aradhya/audit/audit.jsonl[/]"
    )
    console.print()

def render_parasite_candidates(candidates: list[Any], ledger_path: str) -> None:
    """Render the host integration queue."""
    if not candidates:
        render_info("No host integration candidates found.")
        return

    console.print("\n[bold]  Parasite OS - Integration Candidates[/]\n")
    table = Table(
        box=box.ROUNDED,
        border_style="dim",
        show_header=True,
        expand=False,
    )
    table.add_column("#", justify="right", no_wrap=True)
    table.add_column("Repo", style="accent", no_wrap=True)
    table.add_column("Priority", no_wrap=True)
    table.add_column("Score", justify="right", no_wrap=True)
    table.add_column("State", no_wrap=True)
    table.add_column("Capabilities")
    table.add_column("Recommended action")

    for index, candidate in enumerate(candidates, start=1):
        caps = ", ".join(candidate.capabilities[:4])
        if len(candidate.capabilities) > 4:
            caps += f", +{len(candidate.capabilities) - 4}"
        if not caps:
            caps = "[dim]none[/]"

        repo = candidate.repo
        if candidate.archived:
            repo = f"{repo} [dim](archived)[/]"

        table.add_row(
            str(index),
            repo,
            candidate.priority,
            str(candidate.score),
            f"{candidate.completed_stage_count}/7 {candidate.status}",
            caps,
            candidate.recommended_action,
        )

    console.print(table)
    console.print(f"  [dim]Ledger: {ledger_path}[/]")
    console.print("  [dim]Use /parasite inspect <repo> for the exact benefits and next gate.[/]\n")


def render_parasite_inspect(candidate: Any) -> None:
    """Render one host integration candidate."""
    table = Table(
        title=f"[heading]Parasite Candidate: {candidate.repo}[/]",
        box=box.ROUNDED,
        border_style="dim",
        show_header=False,
        expand=False,
    )
    table.add_column("", style="accent", no_wrap=True)
    table.add_column("")
    table.add_row("Path", candidate.host_path)
    table.add_row("Archived", str(candidate.archived))
    table.add_row("Status", f"{candidate.status} ({candidate.completed_stage_count}/7)")
    table.add_row("Priority", f"{candidate.priority} / score {candidate.score}")
    table.add_row("Trust", candidate.trust_score or "unknown")
    table.add_row("Type", candidate.project_type)
    table.add_row("Files", str(candidate.files_scanned))
    table.add_row("Dependencies", str(candidate.dependency_count))
    table.add_row("Capabilities", ", ".join(candidate.capabilities) or "none")
    table.add_row("Integration plan", ", ".join(candidate.integration_plan) or "none")
    table.add_row("Absorbed", str(candidate.absorbed_count))
    table.add_row("Digest", "yes" if candidate.digest_exists else "no")
    table.add_row("Validate", "passed" if candidate.validate_passed else "not passed")
    table.add_row("Absorb", "completed" if candidate.absorb_completed else "not completed")
    if candidate.error:
        table.add_row("Error", f"[error]{candidate.error}[/]")
    table.add_row("Action", candidate.recommended_action)
    table.add_row("Next gate", candidate.next_gate)
    if candidate.description:
        table.add_row("Description", candidate.description)

    console.print(table)
    if candidate.benefits:
        console.print("  [accent]Benefits[/]")
        for benefit in candidate.benefits:
            console.print(f"  - {benefit}")
    if candidate.absorbed_artifacts:
        console.print("  [accent]Absorbed artifacts[/]")
        for artifact in candidate.absorbed_artifacts:
            console.print(f"  - {artifact}")
    console.print()


def render_parasite_status(targets: list[dict[str, Any]]) -> None:
    """Render digestion pipeline status."""
    if not targets:
        render_info("No targets in Hosts/ yet. Clone a repo there or use /parasite digest <name>.")
        return
    console.print("\n[bold]  Parasite OS - Digestion Pipeline Status[/]\n")
    for t in targets:
        stage = t["current_stage"]
        completed = len(t["completed_stages"])
        trust = t.get("trust_score") or "-"
        error = t.get("error")
        if error:
            status_icon = "[error][X][/]"
        elif completed == 7:
            status_icon = "[success][OK][/]"
        elif completed > 0:
            status_icon = "[warning][~][/]"
        else:
            status_icon = "[dim][ ][/]"
        console.print(
            f"  {status_icon} [bold]{t['name']:25s}[/] "
            f"stage: {stage:12s}  "
            f"done: {completed}/7  "
            f"trust: {trust}"
        )
        if error:
            console.print(f"     [error]Error: {error}[/]")
    console.print()


def render_model_ask_result(text: str) -> None:
    """Render a direct response from the model."""
    console.print(f"  [accent]Model >[/] {text}")
    console.print()

def render_daemon_start_success(pid: int, url: str = "http://127.0.0.1:19842") -> None:
    """Render daemon start success message."""
    render_success(f"Daemon started in background (PID: {pid}). API on {url}")

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
