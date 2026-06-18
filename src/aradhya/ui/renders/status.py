"""Dashboard / status renderers: banner, status, topology, federation, model,
health check, and skills list.
"""

from __future__ import annotations

from typing import Any

from rich.panel import Panel
from rich.table import Table
from rich import box

from src.aradhya.ui.console import console, render_success


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


def render_model_ask_result(text: str) -> None:
    """Render a direct response from the model."""
    console.print(f"  [accent]Model >[/] {text}")
    console.print()


def render_daemon_start_success(pid: int, url: str = "http://127.0.0.1:19842") -> None:
    """Render daemon start success message."""
    render_success(f"Daemon started in background (PID: {pid}). API on {url}")


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
