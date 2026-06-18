"""Catalog / list renderers: public API catalog, Parasite OS candidates and
digestion status, and the audit log.
"""

from __future__ import annotations

from typing import Any

from rich.table import Table
from rich import box

from src.aradhya.ui.console import console, render_info


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
