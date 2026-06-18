"""Handlers for the /parasite command family (Parasite OS host digestion).

Extracted from main.py. The public entry point is ``handle_parasite``; it is
wired into main.py's COMMAND_TABLE. Heavy parasite/* modules are imported
lazily inside the handlers so importing this module stays cheap.
"""

from __future__ import annotations

from src.aradhya.paths import get_project_root
from src.aradhya.ui.cli import (
    render_error,
    render_info,
    render_parasite_candidates,
    render_parasite_inspect,
    render_parasite_status,
    render_success,
    render_warning,
)

PROJECT_ROOT = get_project_root()


def _handle_parasite_candidates() -> None:
    from src.aradhya.parasite.ledger import (
        build_integration_ledger,
        write_integration_ledger,
    )
    candidates = build_integration_ledger(PROJECT_ROOT)
    ledger_path = write_integration_ledger(PROJECT_ROOT, candidates)
    render_parasite_candidates(candidates, str(ledger_path))


def _handle_parasite_ledger() -> None:
    from src.aradhya.parasite.ledger import (
        build_integration_ledger,
        write_integration_ledger,
    )
    candidates = build_integration_ledger(PROJECT_ROOT)
    ledger_path = write_integration_ledger(PROJECT_ROOT, candidates)
    render_success(f"Host integration ledger written to: {ledger_path}")
    render_info(f"Candidates indexed: {len(candidates)}")


def _handle_parasite_inspect(target: str) -> None:
    if not target:
        render_error("Usage: /parasite inspect <target>")
        return
    from src.aradhya.parasite.ledger import (
        build_integration_ledger,
        find_candidate,
        write_integration_ledger,
    )
    candidates = build_integration_ledger(PROJECT_ROOT)
    ledger_path = write_integration_ledger(PROJECT_ROOT, candidates)
    candidate = find_candidate(candidates, target)
    if candidate is None:
        render_error(f"No host integration candidate found for '{target}'.")
        render_info(f"Ledger refreshed at: {ledger_path}")
        return
    render_parasite_inspect(candidate)


def _handle_parasite_status(pipeline) -> None:
    targets = pipeline.list_targets()
    render_parasite_status(targets)


def _handle_parasite_digest(pipeline, target: str) -> None:
    if not target:
        render_error("Usage: /parasite digest <target-folder-in-Hosts>")
        return
    target_path = PROJECT_ROOT / "Hosts" / target
    if not target_path.is_dir():
        render_error(f"Target '{target}' not found in Hosts/. Available targets:")
        for child in sorted((PROJECT_ROOT / "Hosts").iterdir()):
            if child.is_dir() and not child.name.startswith("."):
                render_info(f"- {child.name}")
        return

    render_info(f"Digesting: {target}")
    cp = pipeline.digest(target)
    completed = len(cp.completed_stages)
    if cp.error:
        render_error(f"Pipeline stopped at {cp.current_stage}: {cp.error}")
        render_info("Fix the issue and run: /parasite resume " + target)
    else:
        render_success(f"Digestion complete! {completed}/7 stages passed.")
        digest_path = target_path / ".parasite" / "DIGEST.md"
        if digest_path.is_file():
            render_info(f"Digest written to: {digest_path}")


def _handle_parasite_resume(pipeline, target: str) -> None:
    if not target:
        render_error("Usage: /parasite resume <target>")
        return
    cp = pipeline.resume(target)
    if cp is None:
        render_error(f"No checkpoint found for '{target}'. Run /parasite digest {target} first.")
        return
    completed = len(cp.completed_stages)
    if cp.error:
        render_error(f"Pipeline stopped at {cp.current_stage}: {cp.error}")
    else:
        render_success(f"Resumed and completed! {completed}/7 stages passed.")


def _handle_parasite_gc(pipeline, flags: str) -> None:
    apply = "--apply" in flags
    archive = "--archive" in flags
    delete = "--delete" in flags
    mode = "delete" if delete else "archive" if archive else "strip_git"

    if apply:
        from src.aradhya.confirmation_gates import CliConfirmationGate

        approved, _persist = CliConfirmationGate()(
            "parasite_gc",
            {
                "mode": mode,
                "hosts_root": str(PROJECT_ROOT / "Hosts"),
                "effect": "delete/archive/strip files under Hosts",
            },
        )
        if not approved:
            render_warning("Parasite GC cancelled.")
            return

    result = pipeline.gc(
        strip_git=True,
        archive_completed=archive,
        delete_completed=delete,
        dry_run=not apply,
    )

    render_info(
        "Parasite GC dry-run plan"
        if result.get("dry_run")
        else "Parasite GC completed"
    )
    for item in result.get("results", []):
        status = item.get("status", "?")
        action = item.get("action", "?")
        target = item.get("target", "?")
        extra = item.get("dest") or item.get("checkpoint_archive") or item.get("freed_mb", "")
        render_info(f"{status}: {action} {target} {extra}".strip())

    if not result.get("results"):
        render_info("Nothing to clean up.")
    for error in result.get("errors", []):
        render_error(f"{error.get('action')} failed for {error.get('target')}: {error.get('error')}")
    if result.get("dry_run"):
        render_info("Re-run with --apply after reviewing the plan.")
    else:
        render_success(
            f"GC actions taken: {result.get('actions_taken', 0)}; "
            f"space affected: {result.get('freed_mb', '0.0')} MB"
        )


def _handle_parasite_absorb(pipeline, absorb_arg: str) -> None:
    targets_to_absorb: list[str] = []
    if absorb_arg == "--all":
        for item in pipeline.list_targets():
            if len(item.get("completed_stages", [])) == 7:
                targets_to_absorb.append(item["name"])
    elif absorb_arg:
        targets_to_absorb = [absorb_arg]
    else:
        render_error("Usage: /parasite absorb <target> or /parasite absorb --all")
        return

    render_info(f"Re-running ABSORB for {len(targets_to_absorb)} host(s)")
    for target_name in targets_to_absorb:
        cp = pipeline.reabsorb(target_name)
        if cp and not cp.error:
            absorbed = cp.stage_results.get("ABSORB", {}).get("artifacts", {})
            count = absorbed.get("count", 0)
            render_success(f"{target_name}: {count} artifact(s) absorbed")
        elif cp and cp.error:
            render_error(f"{target_name}: {cp.error}")
        else:
            render_warning(f"{target_name}: no checkpoint")


def _handle_parasite_dedup(flags: str) -> None:
    from src.aradhya.parasite.deduplicator import SkillDeduplicator

    apply = "--apply" in flags
    gate = None
    if apply:
        from src.aradhya.confirmation_gates import CliConfirmationGate
        gate = CliConfirmationGate()

    render_info(
        "Scanning for duplicate skills"
        + (" and applying confirmed merges" if apply else " (dry-run)")
    )
    deduper = SkillDeduplicator(PROJECT_ROOT, confirmation_gate=gate)
    actions = deduper.run_deduplication(dry_run=not apply)
    if not actions:
        render_info("No duplicate skills found.")
        return

    merged = 0
    for action in actions:
        status = action.get("status", "planned")
        if status == "merged":
            merged += 1
        render_info(
            f"{status}: {action.get('duplicate')} -> {action.get('base')}"
        )
    if apply:
        render_success(f"Deduplication complete. Merged {merged} skill(s).")
    else:
        render_info("Dry run only. Re-run with /parasite dedup --apply to merge.")


def handle_parasite(*, command: str) -> None:
    """Handle /parasite digestion and host-integration commands."""
    from src.aradhya.parasite.pipeline import DigestionPipeline

    normalized = command.strip().lower()
    pipeline = DigestionPipeline(PROJECT_ROOT)

    def _ptail(*prefixes: str) -> str:
        for prefix in prefixes:
            if normalized.startswith(prefix):
                return command.strip()[len(prefix):].strip()
        return ""

    if normalized in {"/parasite candidates", "parasite candidates"}:
        return _handle_parasite_candidates()

    if normalized in {"/parasite ledger", "parasite ledger"}:
        return _handle_parasite_ledger()

    if normalized.startswith("/parasite inspect") or normalized.startswith("parasite inspect"):
        return _handle_parasite_inspect(_ptail("/parasite inspect", "parasite inspect"))

    if normalized in {"/parasite", "/parasite status", "parasite status", "parasite"}:
        return _handle_parasite_status(pipeline)

    if normalized.startswith("/parasite digest") or normalized.startswith("parasite digest"):
        return _handle_parasite_digest(pipeline, _ptail("/parasite digest", "parasite digest"))

    if normalized.startswith("/parasite resume") or normalized.startswith("parasite resume"):
        return _handle_parasite_resume(pipeline, _ptail("/parasite resume", "parasite resume"))

    if normalized.startswith("/parasite gc") or normalized.startswith("parasite gc"):
        return _handle_parasite_gc(pipeline, _ptail("/parasite gc", "parasite gc").lower())

    if normalized.startswith("/parasite absorb") or normalized.startswith("parasite absorb"):
        return _handle_parasite_absorb(pipeline, _ptail("/parasite absorb", "parasite absorb"))

    if normalized.startswith("/parasite dedup") or normalized.startswith("parasite dedup"):
        return _handle_parasite_dedup(_ptail("/parasite dedup", "parasite dedup").lower())

    render_error(
        "Usage: /parasite [status|candidates|inspect <target>|ledger|digest <target>|"
        "resume <target>|gc [--archive|--delete] [--apply]|absorb <target>|"
        "absorb --all|dedup [--apply]]"
    )
