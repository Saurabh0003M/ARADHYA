"""Interactive CLI entry point for the Aradhya assistant core."""

from __future__ import annotations

from pathlib import Path
import subprocess
import inspect
import sys
import threading
import time

from loguru import logger

if __package__ in {None, ""}:
    project_root = Path(__file__).resolve().parents[2]
    project_root_str = str(project_root)
    if project_root_str not in sys.path:
        sys.path.insert(0, project_root_str)

from src.aradhya.paths import get_project_root
from src.aradhya.assistant_core import AradhyaAssistant
from src.aradhya.assistant_models import PlanKind, WakeSource
from src.aradhya.utils.cache_diagnostics import (
    format_cache_validation_report,
    run_cache_validation,
)
from src.aradhya.ui.cli import (
    console,
    render_banner,
    render_error,
    render_health_check,
    render_help,
    render_info,
    render_response,
    render_skills_list,
    render_status,
    render_topology,
    render_federation_status,
    render_federation_doctor,
    render_model_workers,
    render_cloud_safety_assessment,
    render_api_categories,
    render_api_entries,
    render_api_entry,
    render_success,
    VoiceStatusConfig,
    render_voice_status,
    render_warning,
    prompt_input,
    render_stream,
    render_audit,
    render_parasite_candidates,
    render_parasite_inspect,
    render_parasite_status,
    render_model_ask_result,
    render_daemon_start_success,
)
from src.aradhya.utils.logging import configure_logging
from src.aradhya.model_setup import bootstrap_runtime_profile, render_model_health
from src.aradhya.model_provider import build_text_model_provider
from src.aradhya.runtime_profile import load_runtime_profile
from src.aradhya.cloud_safety import CloudPrivacyGate
from src.aradhya.model_workers import ModelWorkerRegistry
from src.aradhya.api_catalog import PublicApiCatalog
from src.aradhya.topology import ensure_topology, topology_path
from src.aradhya.federation import FederationManager
from src.aradhya.skills import load_skills
from src.aradhya.voice.activation import (
    VoiceActivatedAradhya,
    describe_voice_activation_support,
)
from src.aradhya.voice.pipeline import VoiceInboxManager
from src.aradhya.voice.wake_word import WakeWordListener
from src.aradhya.audit_logger import get_audit_logger

PROJECT_ROOT = get_project_root()
IPC_FILE = PROJECT_ROOT / ".aradhya_ipc"
IPC_QUEUE_FILE = PROJECT_ROOT / ".aradhya_ipc_queue"   # atomic append-only queue
HEARTBEAT_FILE = PROJECT_ROOT / ".aradhya_heartbeat"   # touched by heartbeat thread
MAX_DIRECT_MODEL_PROMPT_CHARS = 4000

# ── Gap D: Session heartbeat (NanoClaw pattern) ──────────────────────
_HEARTBEAT_INTERVAL = 30   # seconds between touches
_heartbeat_stop = threading.Event()


def _heartbeat_worker() -> None:
    """Touch HEARTBEAT_FILE every _HEARTBEAT_INTERVAL seconds.

    The daemon's /health endpoint checks this file's mtime to detect
    a frozen CLI session (no heartbeat for >90 s → reported as stale).
    Inspired by NanoClaw's container heartbeat mechanism.
    """
    while not _heartbeat_stop.wait(_HEARTBEAT_INTERVAL):
        try:
            HEARTBEAT_FILE.touch()
        except OSError:
            pass   # non-fatal — file system issues must not crash the agent


def _start_heartbeat() -> threading.Thread:
    """Start the heartbeat background thread and return it."""
    HEARTBEAT_FILE.touch()   # immediate first touch at startup
    t = threading.Thread(
        target=_heartbeat_worker,
        name="aradhya-heartbeat",
        daemon=True,
    )
    t.start()
    return t


def _stop_heartbeat() -> None:
    """Signal the heartbeat thread to stop and clean up the heartbeat file."""
    _heartbeat_stop.set()
    try:
        HEARTBEAT_FILE.unlink(missing_ok=True)
    except OSError:
        pass


def _response_was_streamed(resp) -> bool:
    """Return True when the live stream renderer already printed the reply."""

    if resp.awaiting_confirmation or resp.result is None or not resp.result.success:
        return False
    if resp.plan is None:
        return False
    return resp.plan.kind in {PlanKind.AGENT_TASK, PlanKind.GENERAL_CHAT}


# ── Startup health checks ────────────────────────────────────────────

def _run_health_checks(runtime_profile, model_provider) -> list[tuple[str, bool, str]]:
    """Run startup diagnostics and return a list of (name, passed, msg)."""
    checks: list[tuple[str, bool, str]] = []

    # 1. Python version
    v = sys.version_info
    ok = v >= (3, 10)
    checks.append((
        "Python",
        ok,
        f"{v.major}.{v.minor}.{v.micro}" + ("" if ok else " - need 3.10+"),
    ))

    # 2. Ollama reachability + model
    try:
        health = model_provider.health_check()
        model_ok = getattr(health, "ready", False)
        model_name = runtime_profile.model.model_name
        if model_ok:
            checks.append(("Ollama", True, f"Ready - {model_name}"))
        else:
            msg = getattr(health, "error", "unreachable")
            checks.append(("Ollama", False, f"Offline - {msg}"))
    except Exception as exc:
        checks.append(("Ollama", False, f"Error - {exc}"))

    # 3. Config files
    prefs_path = PROJECT_ROOT / "core" / "config" / "preferences.json"
    if not prefs_path.is_file():
        prefs_path = PROJECT_ROOT / "core" / "memory" / "preferences.json"
    profile_path = PROJECT_ROOT / "core" / "config" / "profile.json"
    if not profile_path.is_file():
        profile_path = PROJECT_ROOT / "core" / "memory" / "profile.json"
    checks.append((
        "Preferences",
        prefs_path.is_file(),
        str(prefs_path.name) if prefs_path.is_file() else "MISSING",
    ))
    checks.append((
        "Profile",
        profile_path.is_file(),
        str(profile_path.name) if profile_path.is_file() else "MISSING",
    ))

    # 4. Voice inbox
    inbox = Path(runtime_profile.voice.audio_inbox_dir)
    if not inbox.is_absolute():
        inbox = PROJECT_ROOT / inbox
    checks.append((
        "Voice Inbox",
        inbox.is_dir(),
        str(inbox) if inbox.is_dir() else "Will be created on first use",
    ))

    return checks


# ── Command handlers ──────────────────────────────────────────────────

def _handle_help(*, command: str) -> None:
    normalized = command.strip().lower()
    topic = None
    if normalized.startswith("/help "):
        topic = command.strip()[6:].strip()
    elif normalized.startswith("help "):
        topic = command.strip()[5:].strip()
    render_help(topic)


def _handle_mentor(*, assistant, command: str) -> None:
    """/mentor [do|teach] [skill_level] — switch how Aradhya helps."""
    rest = command.strip()
    for prefix in ("/mentor", "mentor"):
        if rest.lower().startswith(prefix):
            rest = rest[len(prefix):].strip()
            break

    if not rest:
        state = assistant.state
        level = f", skill level '{state.skill_level}'" if state.skill_level else ""
        render_info(
            f"Mentor mode is '{state.mentor_mode}'{level}. "
            "Use /mentor do or /mentor teach [beginner|intermediate|advanced]."
        )
        return

    parts = rest.split()
    mode = parts[0]
    skill_level = parts[1] if len(parts) > 1 else None
    try:
        message = assistant.set_mentor_mode(mode, skill_level)
    except ValueError as error:
        render_error(str(error))
        return
    render_info(message)


def _handle_status(*, assistant, runtime_profile, model_provider,
                   live_voice_runtime) -> None:
    model_ok = None
    try:
        health = model_provider.health_check()
        model_ok = getattr(health, "ready", False)
    except Exception:
        model_ok = False

    render_status(
        is_awake=assistant.state.is_awake,
        model_provider_name=runtime_profile.model.provider,
        model_name=runtime_profile.model.model_name,
        model_ok=model_ok,
        pending_plan=assistant.state.pending_plan,
        voice_provider=runtime_profile.voice.provider,
        voice_running=bool(live_voice_runtime and live_voice_runtime.is_running()),
        skills_active=assistant.skill_registry.active_count if assistant.skill_registry else 0,
        skills_total=assistant.skill_registry.count if assistant.skill_registry else 0,
        live_execution=assistant.preferences.allow_live_execution,
    )


def _handle_topology(*, runtime_profile, command) -> None:
    normalized = command.strip().lower()
    refreshed = normalized.startswith("/topology rescan") or normalized.startswith("topology rescan")
    topology = ensure_topology(PROJECT_ROOT, runtime_profile, force=refreshed)
    render_topology(
        topology,
        path=str(topology_path(PROJECT_ROOT)),
        refreshed=refreshed,
    )


def _federation_manager(runtime_profile) -> FederationManager:
    return FederationManager(PROJECT_ROOT, runtime_profile)


def _handle_federation_init(*, runtime_profile) -> None:
    manager = _federation_manager(runtime_profile)
    manager.initialize()
    render_success("Federation foundation initialized for LAN-only mode.")
    render_federation_status(manager.status())


def _handle_federation_status(*, runtime_profile) -> None:
    manager = _federation_manager(runtime_profile)
    render_federation_status(manager.status())


def _handle_federation_doctor(*, runtime_profile) -> None:
    manager = _federation_manager(runtime_profile)
    render_federation_doctor(manager.doctor())


def _handle_sleep(*, assistant) -> None:
    resp = assistant.go_idle()
    render_response(resp.spoken_response)


def _handle_voice_status(*, voice_manager, runtime_profile,
                         live_voice_runtime) -> None:
    status = voice_manager.status()
    activation_support = describe_voice_activation_support(runtime_profile)
    config = VoiceStatusConfig(
        status=status,
        activation_support=activation_support,
        runtime_profile=runtime_profile,
        voice_running=bool(live_voice_runtime and live_voice_runtime.is_running()),
    )
    render_voice_status(config)


def _handle_voice_process(*, assistant, voice_manager) -> None:
    results = voice_manager.process_pending_audio()
    if not results:
        render_info("No pending audio files in the inbox.")
        return
    for result in results:
        render_info(result.message)
        if result.transcript_path is not None:
            render_info(f"Transcript saved to {result.transcript_path}")
        if result.archived_audio_path is not None:
            render_info(f"Archived audio to {result.archived_audio_path}")
        if result.transcript_text:
            render_info(f"Transcript: {result.transcript_text}")
            if assistant.state.is_awake:
                resp = assistant.handle_transcript(result.transcript_text)
                render_response(resp.spoken_response, resp.transcript_echo,
                                resp.awaiting_confirmation)
            else:
                render_warning("Transcript saved. Wake Aradhya to route voice into planning.")


def _handle_voice_activate(*, assistant, voice_manager, runtime_profile,
                           ctx) -> None:
    try:
        if ctx.get("live_voice_runtime") is None:
            ctx["live_voice_runtime"] = VoiceActivatedAradhya(
                assistant=assistant,
                voice_manager=voice_manager,
                runtime_profile=runtime_profile,
                output_handler=print,
            )
        ctx["live_voice_runtime"].start()
    except Exception as error:
        render_error(f"Live activation failed: {error}")


def _handle_voice_stop(*, ctx) -> None:
    lvr = ctx.get("live_voice_runtime")
    if lvr and lvr.is_running():
        lvr.stop()
    else:
        render_info("Live voice activation is not running.")


def _handle_wake_word_on(*, assistant, voice_manager, ctx) -> None:
    if ctx.get("wake_word_listener") is None:
        ctx["wake_word_listener"] = WakeWordListener(
            assistant=assistant, voice_manager=voice_manager,
        )
    ctx["wake_word_listener"].start()
    render_success("Wake word detection enabled (listening for 'wakeup').")


def _handle_wake_word_off(*, ctx) -> None:
    wl = ctx.get("wake_word_listener")
    if wl:
        wl.stop()
    render_success("Wake word detection disabled.")


def _handle_model_ping(*, model_provider) -> None:
    render_model_health(model_provider.health_check())


def _handle_model_workers(*, runtime_profile, command) -> None:
    normalized = command.strip().lower()
    assess_prefixes = ("/model workers assess", "model workers assess")
    if any(normalized.startswith(prefix) for prefix in assess_prefixes):
        text = command
        for prefix in assess_prefixes:
            if normalized.startswith(prefix):
                text = command[len(prefix):].strip()
                break
        if not text:
            render_error("Usage: /model workers assess <text>")
            return
        assessment = CloudPrivacyGate().assess_text(text, source="/model workers assess")
        render_cloud_safety_assessment(assessment)
        return

    registry = ModelWorkerRegistry(PROJECT_ROOT, runtime_profile)
    render_model_workers(registry.statuses())


def _handle_model_ask(*, command, model_provider, runtime_profile) -> None:
    prompt = command[len("/model ask "):].strip()
    if not prompt:
        prompt = command[len("model ask "):].strip()
    normalized = " ".join(prompt.split())
    if not normalized:
        render_error("Add a prompt after '/model ask'.")
        return
    if len(normalized) > MAX_DIRECT_MODEL_PROMPT_CHARS:
        render_error(f"Direct model prompts must stay under {MAX_DIRECT_MODEL_PROMPT_CHARS} characters.")
        return
    if runtime_profile.model.provider.lower() == "openrouter":
        assessment = CloudPrivacyGate().assess_text(normalized, source="/model ask")
        if not assessment.allowed:
            render_cloud_safety_assessment(assessment)
            return
    try:
        result = model_provider.generate(normalized)
        render_model_ask_result(result.text)
    except Exception as error:
        render_error(f"Generation failed: {error}")


def _handle_skills_list(*, skill_registry) -> None:
    all_skills = skill_registry.all_skills() if skill_registry else []
    render_skills_list(all_skills)


def _handle_skills_enable(*, command, skill_registry) -> None:
    name = command.split(maxsplit=2)[-1].strip() if len(command.split()) > 2 else ""
    if not name:
        render_error("Usage: /skills enable <name>")
        return
    if skill_registry and skill_registry.enable(name):
        render_success(f"Enabled '{name}'.")
    else:
        render_error(f"Skill '{name}' not found.")


def _handle_skills_disable(*, command, skill_registry) -> None:
    name = command.split(maxsplit=2)[-1].strip() if len(command.split()) > 2 else ""
    if not name:
        render_error("Usage: /skills disable <name>")
        return
    if skill_registry and skill_registry.disable(name):
        render_success(f"Disabled '{name}'.")
    else:
        render_error(f"Skill '{name}' not found.")


def _handle_icon_on(*, ctx) -> None:
    fp = ctx.get("floating_icon_process")
    if fp is None or fp.poll() is not None:
        try:
            ctx["floating_icon_process"] = subprocess.Popen(
                [sys.executable, "-m", "src.aradhya.ui.floating_icon"],
                cwd=str(PROJECT_ROOT),
            )
            render_success("Floating icon enabled.")
        except Exception as error:
            render_error(f"Failed to start floating icon: {error}")
    else:
        render_info("Floating icon is already running.")


def _handle_icon_off(*, ctx) -> None:
    fp = ctx.get("floating_icon_process")
    if fp and fp.poll() is None:
        fp.terminate()
        ctx["floating_icon_process"] = None
        render_success("Floating icon disabled.")
    else:
        render_info("Floating icon is not running.")


def _handle_cache(*, assistant) -> None:
    report = run_cache_validation(assistant.preferences)
    for line in format_cache_validation_report(report):
        render_info(line)


def _handle_apis(*, command) -> None:
    catalog = PublicApiCatalog(PROJECT_ROOT)
    normalized = command.strip().lower()

    def _tail(*prefixes: str) -> str:
        for prefix in prefixes:
            if normalized.startswith(prefix):
                return command[len(prefix):].strip()
        return ""

    if normalized in {"/apis", "apis"}:
        render_api_categories(catalog.source, catalog.categories())
        return

    if normalized.startswith("/apis search") or normalized.startswith("apis search"):
        query = _tail("/apis search", "apis search")
        if not query:
            render_error("Usage: /apis search <query>")
            return
        entries = catalog.search(query)
        render_api_entries(
            f"API Search: {query}",
            entries,
            {entry.name: catalog.risk_label(entry) for entry in entries},
        )
        return

    if normalized.startswith("/apis category") or normalized.startswith("apis category"):
        category = _tail("/apis category", "apis category")
        if not category:
            render_error("Usage: /apis category <name>")
            return
        entries = catalog.by_category(category)
        render_api_entries(
            f"API Category: {category}",
            entries,
            {entry.name: catalog.risk_label(entry) for entry in entries},
        )
        return

    if normalized.startswith("/apis inspect") or normalized.startswith("apis inspect"):
        name = _tail("/apis inspect", "apis inspect")
        if not name:
            render_error("Usage: /apis inspect <name>")
            return
        entry = catalog.inspect(name)
        if entry is None:
            render_info("No matching API entry in the local catalog.")
            return
        render_api_entry(entry, catalog.risk_label(entry))
        return

    if normalized.startswith("/apis recommend") or normalized.startswith("apis recommend"):
        need = _tail("/apis recommend", "apis recommend")
        if not need:
            render_error("Usage: /apis recommend <need>")
            return
        entries = catalog.recommend(need)
        render_api_entries(
            f"API Recommendations: {need}",
            entries,
            {entry.name: catalog.risk_label(entry) for entry in entries},
        )
        return

    render_error("Usage: /apis [search|category|inspect|recommend] ...")


def _handle_telegram_start(*, assistant, ctx) -> None:
    if ctx.get("telegram_bot") and ctx["telegram_bot"].is_running():
        render_info("Telegram bot is already running.")
        return
    try:
        from src.aradhya.channels.telegram import AradhyaTelegramBot, _load_telegram_config
        config = _load_telegram_config()
        if not config["bot_token"]:
            render_error(
                "No Telegram token. Set ARADHYA_TELEGRAM_TOKEN env var "
                "or add telegram.bot_token to profile.json"
            )
            return
        bot = AradhyaTelegramBot(
            token=config["bot_token"],
            allowed_user_ids=config.get("allowed_user_ids", []),
            assistant=assistant,
        )
        bot.start()
        ctx["telegram_bot"] = bot
        render_success("Telegram bot started. Send /start to your bot on Telegram.")
    except Exception as error:
        render_error(f"Failed to start Telegram bot: {error}")


def _handle_telegram_stop(*, ctx) -> None:
    bot = ctx.get("telegram_bot")
    if bot and bot.is_running():
        bot.stop()
        ctx["telegram_bot"] = None
        render_success("Telegram bot stopped.")
    else:
        render_info("Telegram bot is not running.")


def _handle_audit() -> None:
    audit = get_audit_logger()
    entries = audit.recent_entries(20)
    if not entries:
        render_info("No audit entries yet.")
        return

    tool_entries = [e for e in entries if e.get("type") == "tool_call"]
    tool_ok = sum(1 for e in tool_entries if e.get("success"))
    tool_fail = len(tool_entries) - tool_ok
    security_entries = [e for e in entries if e.get("type") == "security"]
    sessions = {e.get("session_id", "") for e in entries if e.get("session_id")}
    last_session = (sorted(sessions) or ["-"])[-1]

    render_audit(
        entries=entries,
        last_session=last_session,
        tool_ok=tool_ok,
        tool_fail=tool_fail,
        security_count=len(security_entries),
    )


def _handle_daemon_start(*, ctx) -> None:
    dp = ctx.get("daemon_process")
    if dp and dp.poll() is None:
        render_info("Daemon is already running.")
        return
    try:
        flags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
        ctx["daemon_process"] = subprocess.Popen(
            [sys.executable, "-m", "src.aradhya.daemon"],
            cwd=str(PROJECT_ROOT),
            creationflags=flags,
        )
        render_daemon_start_success(ctx["daemon_process"].pid)
    except Exception as error:
        render_error(f"Failed to start daemon: {error}")


def _handle_daemon_stop(*, ctx) -> None:
    dp = ctx.get("daemon_process")
    if dp and dp.poll() is None:
        dp.terminate()
        ctx["daemon_process"] = None
        render_success("Daemon stopped.")
    else:
        render_info("Daemon is not running from this session.")


def _handle_setup() -> None:
    try:
        from src.aradhya.setup_wizard import run_wizard
        run_wizard()
    except Exception as error:
        render_error(f"Setup wizard failed: {error}")




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


def _handle_parasite(*, command) -> None:
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


# ── Command dispatch ──────────────────────────────────────────────────

# Maps slash commands and their legacy equivalents to handlers.
# The dispatch logic tries longest match first so "/voice process"
# beats "/voice".

COMMAND_TABLE: list[tuple[list[str], callable]] = [
    # Core
    (["/help", "help"], _handle_help),
    (["/status"], _handle_status),
    (["/mentor"], _handle_mentor),
    (["/topology rescan", "topology rescan"], _handle_topology),
    (["/topology", "topology"], _handle_topology),
    (["/federation doctor", "federation doctor"], _handle_federation_doctor),
    (["/federation init", "federation init"], _handle_federation_init),
    (["/federation status", "federation status", "/federation", "federation"], _handle_federation_status),
    (["/sleep", "sleep"], _handle_sleep),

    # Voice (order matters — longer prefixes first)
    (["/voice process", "voice process"], _handle_voice_process),
    (["/voice activate", "voice activate"], _handle_voice_activate),
    (["/voice stop", "voice stop"], _handle_voice_stop),
    (["/voice", "voice status"], _handle_voice_status),

    # Wake word
    (["/wake-word on", "wake word enable"], _handle_wake_word_on),
    (["/wake-word off", "wake word disable"], _handle_wake_word_off),

    # Model (longer prefix first)
    (["/model workers assess", "model workers assess"], _handle_model_workers),
    (["/model workers", "model workers"], _handle_model_workers),
    (["/model ask", "model ask"], _handle_model_ask),
    (["/model", "model ping"], _handle_model_ping),

    # Skills (longer prefix first)
    (["/skills enable", "skills enable"], _handle_skills_enable),
    (["/skills disable", "skills disable"], _handle_skills_disable),
    (["/skills", "skills list"], _handle_skills_list),

    # Icon
    (["/icon on", "icon enable"], _handle_icon_on),
    (["/icon off", "icon disable"], _handle_icon_off),

    # Cache
    (["/cache", "cache validate"], _handle_cache),

    # Parasite OS (longer prefix first)
    (["/parasite candidates", "parasite candidates"], _handle_parasite),
    (["/parasite inspect", "parasite inspect"], _handle_parasite),
    (["/parasite ledger", "parasite ledger"], _handle_parasite),
    (["/parasite digest", "parasite digest"], _handle_parasite),
    (["/parasite resume", "parasite resume"], _handle_parasite),
    (["/parasite absorb", "parasite absorb"], _handle_parasite),
    (["/parasite gc", "parasite gc"], _handle_parasite),
    (["/parasite dedup", "parasite dedup"], _handle_parasite),
    (["/parasite status", "parasite status", "/parasite", "parasite"], _handle_parasite),

    # API catalog
    (["/apis", "apis"], _handle_apis),

    # Telegram
    (["/telegram start", "/telegram on"], _handle_telegram_start),
    (["/telegram stop", "/telegram off"], _handle_telegram_stop),

    # Audit
    (["/audit"], _handle_audit),

    # Daemon
    (["/daemon start", "/daemon on"], _handle_daemon_start),
    (["/daemon stop", "/daemon off"], _handle_daemon_stop),

    # Setup
    (["/setup"], _handle_setup),
]


def _dispatch_command(command: str, **kwargs) -> bool:
    """Try to match a slash or legacy command. Returns True if handled."""
    normalized = command.strip().lower()
    for prefixes, handler in COMMAND_TABLE:
        for prefix in prefixes:
            if normalized == prefix or normalized.startswith(prefix + " "):
                sig = inspect.signature(handler).parameters
                has_varkw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.values())
                all_kwargs = dict(command=command, **kwargs)
                if has_varkw:
                    filtered = all_kwargs
                else:
                    filtered = {k: v for k, v in all_kwargs.items() if k in sig}
                handler(**filtered)
                return True
    return False


# ── IPC watcher ───────────────────────────────────────────────────────
# Uses an append-only queue file (.aradhya_ipc_queue) instead of a
# single-shot file.  The watcher atomically reads all pending lines,
# processes each command in order, then truncates the queue.
# This eliminates the race condition where a rapid second press was
# silently dropped because the file was unlinked before being read.

IPC_QUEUE_FILE = PROJECT_ROOT / ".aradhya_ipc_queue"

def _start_ipc_watcher(assistant, voice_manager, runtime_profile, ctx):
    """Background thread that reads commands from the floating icon."""

    def _dispatch_ipc(cmd: str) -> None:
        """Execute a single IPC command string."""
        if cmd == "wake":
            console.print()
            resp = assistant.handle_wake(WakeSource.FLOATING_ICON)
            render_response(resp.spoken_response)
        elif cmd == "sleep":
            console.print()
            resp = assistant.go_idle()
            render_response(resp.spoken_response)
        elif cmd == "voice_toggle":
            console.print()
            lvr = ctx.get("live_voice_runtime")
            if lvr and lvr.is_running():
                lvr.stop()
            else:
                if lvr is None:
                    lvr = VoiceActivatedAradhya(
                        assistant=assistant,
                        voice_manager=voice_manager,
                        runtime_profile=runtime_profile,
                        output_handler=print,
                    )
                    ctx["live_voice_runtime"] = lvr
                lvr.start()
        elif cmd == "debate_toggle":
            console.print()
            transcript = (
                "disable debate mode"
                if assistant.state.debate_mode_enabled
                else "enable debate mode"
            )
            resp = assistant.handle_transcript(transcript)
            render_response(
                resp.spoken_response,
                transcript_echo=resp.transcript_echo,
                awaiting=resp.awaiting_confirmation,
            )
        elif cmd in {"screen_watch_toggle", "browser_toggle"}:
            console.print()
            render_warning(
                "That floating-icon button is visible, but its screen/browser "
                "watch backend is not implemented yet."
            )
        elif cmd in {"lock_screen", "prevent_sleep"}:
            console.print()
            render_warning(
                f"Floating-icon command '{cmd}' is not wired to a safe "
                "confirmed action yet."
            )
        elif cmd == "exit_icon":
            console.print()
            render_info("Floating icon closed.")
        elif cmd:
            console.print()
            render_warning(f"Unknown floating-icon command: {cmd}")

    def watcher():
        while ctx.get("ipc_running", True):
            # Legacy single-file support (backward compat)
            if IPC_FILE.exists():
                try:
                    cmd = IPC_FILE.read_text(encoding="utf-8").strip()
                    IPC_FILE.unlink(missing_ok=True)
                    _dispatch_ipc(cmd)
                except Exception as error:
                    console.print()
                    render_warning(f"Floating-icon command failed: {error}")

            # New queue-file: read all lines atomically then truncate
            if IPC_QUEUE_FILE.exists():
                try:
                    raw = IPC_QUEUE_FILE.read_text(encoding="utf-8")
                    # Truncate before processing so new commands can append
                    IPC_QUEUE_FILE.write_text("", encoding="utf-8")
                    for line in raw.splitlines():
                        cmd = line.strip()
                        if cmd:
                            try:
                                _dispatch_ipc(cmd)
                            except Exception as error:
                                console.print()
                                render_warning(f"Floating-icon command failed: {error}")
                except Exception as error:
                    console.print()
                    render_warning(f"IPC queue read failed: {error}")

            time.sleep(0.25)   # Faster polling with queue — 250 ms

    t = threading.Thread(target=watcher, daemon=True)
    t.start()
    return t


def _setup_environment():
    runtime_profile = load_runtime_profile(PROJECT_ROOT)
    log_path = configure_logging(PROJECT_ROOT)
    runtime_profile = bootstrap_runtime_profile(runtime_profile, PROJECT_ROOT)
    model_provider = build_text_model_provider(runtime_profile.model)
    skill_registry = load_skills(PROJECT_ROOT)
    assistant = AradhyaAssistant.from_project_root(
        PROJECT_ROOT,
        model_provider=model_provider,
        skill_registry=skill_registry,
    )
    voice_manager = VoiceInboxManager(runtime_profile.voice)
    voice_manager.ensure_directories()

    # Mutable context shared with IPC watcher and command handlers
    ctx: dict = {
        "live_voice_runtime": None,
        "floating_icon_process": None,
        "wake_word_listener": None,
        "ipc_running": True,
    }

    logger.info(
        "Aradhya CLI started with model {} and voice provider {}",
        runtime_profile.model.model_name,
        runtime_profile.voice.provider,
    )

    # ── Beautiful startup ─────────────────────────────────────────────
    console.print()
    render_banner(
        model_name=runtime_profile.model.model_name,
        voice_inbox=str(runtime_profile.voice.audio_inbox_dir),
        skills_active=skill_registry.active_count if skill_registry else 0,
        skills_total=skill_registry.count if skill_registry else 0,
        log_path=str(log_path),
    )

    # ── Startup health checks ─────────────────────────────────────────
    checks = _run_health_checks(runtime_profile, model_provider)
    has_failures = any(not ok for _, ok, _ in checks)
    if has_failures:
        render_health_check(checks)

    # ── Auto-wake ─────────────────────────────────────────────────────
    # The #1 usability complaint: users had to type 'wake' before
    # Aradhya would do anything.  Now it wakes automatically.
    assistant.state.is_awake = True
    assistant.state.pending_plan = None
    if assistant.preferences.directory_index_policy.refresh_on_wake:
        try:
            assistant.index_manager.refresh_if_stale("wake")
        except Exception:
            pass
    logger.info("Aradhya auto-woke on startup")

    # ── Optional auto-start voice ─────────────────────────────────────
    if runtime_profile.voice_activation.enabled_on_startup:
        try:
            ctx["live_voice_runtime"] = VoiceActivatedAradhya(
                assistant=assistant,
                voice_manager=voice_manager,
                runtime_profile=runtime_profile,
                output_handler=print,
            )
            ctx["live_voice_runtime"].start()
        except Exception as error:
            render_warning(f"Voice auto-start failed: {error}")

    # ── IPC watcher for floating icon ─────────────────────────────────
    _start_ipc_watcher(assistant, voice_manager, runtime_profile, ctx)

    return assistant, model_provider, runtime_profile, voice_manager, skill_registry, ctx


def _run_cli_loop(handler_kwargs: dict):
    ctx = handler_kwargs["ctx"]
    assistant = handler_kwargs["assistant"]
    voice_manager = handler_kwargs["voice_manager"]
    runtime_profile = handler_kwargs["runtime_profile"]

    while True:
        try:
            command = prompt_input().strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            render_info("Shutting down.")
            break

        if not command:
            continue

        normalized = command.lower().strip()

        # Exit
        if normalized == "exit":
            render_info("Shutting down.")
            break

        # Update live_voice_runtime reference in handler_kwargs
        handler_kwargs["live_voice_runtime"] = ctx.get("live_voice_runtime")

        # Try slash/legacy command dispatch
        if _dispatch_command(command, **handler_kwargs):
            continue

        # Legacy wake commands — still supported but no longer needed
        if normalized in {"wake", "ctrl+win"}:
            source = (
                WakeSource.HOTKEY if normalized == "ctrl+win"
                else WakeSource.FLOATING_ICON
            )
            resp = assistant.handle_wake(source)
            render_response(resp.spoken_response)
            if runtime_profile.voice.poll_on_wake:
                pending_audio = voice_manager.status().pending_audio
                if pending_audio:
                    render_info(
                        f"{len(pending_audio)} pending audio file(s) in "
                        f"{runtime_profile.voice.audio_inbox_dir}"
                    )
            continue

        # ── Natural language input ────────────────────────────────
        # Everything that isn't a command goes to the assistant planner.
        resp = assistant.handle_transcript(command, stream_handler=render_stream, session_name=handler_kwargs["session_name"])

        spoken = "" if _response_was_streamed(resp) else resp.spoken_response
        if resp.transcript_echo or resp.awaiting_confirmation or spoken:
            render_response(
                spoken,
                transcript_echo=resp.transcript_echo,
                awaiting=resp.awaiting_confirmation,
            )


# ── Main entry point ──────────────────────────────────────────────────

def main() -> None:
    import argparse  # noqa: PLC0415
    parser = argparse.ArgumentParser(description="Aradhya CLI", add_help=False)
    parser.add_argument(
        "--session",
        default="main",
        metavar="NAME",
        help="Named session to use (default: main). Use 'telegram' for the Telegram bot, etc.",
    )
    args, _ = parser.parse_known_args()
    session_name: str = args.session

    assistant, model_provider, runtime_profile, voice_manager, skill_registry, ctx = _setup_environment()

    # ── Gap D: Session heartbeat (NanoClaw pattern) ───────────────────
    _start_heartbeat()

    # ── Shared kwargs for all command handlers ────────────────────────
    handler_kwargs = dict(
        assistant=assistant,
        model_provider=model_provider,
        runtime_profile=runtime_profile,
        voice_manager=voice_manager,
        skill_registry=skill_registry,
        live_voice_runtime=ctx.get("live_voice_runtime"),
        ctx=ctx,
        session_name=session_name,   # Gap G: named per-channel session
    )

    # ── Main input loop ───────────────────────────────────────────────
    try:
        handler_kwargs["session_name"] = session_name
        _run_cli_loop(handler_kwargs)
    finally:
        _stop_heartbeat()   # remove heartbeat file on clean shutdown
        ctx["ipc_running"] = False
        wl = ctx.get("wake_word_listener")
        if wl:
            wl.stop()
        lvr = ctx.get("live_voice_runtime")
        if lvr and lvr.is_running():
            lvr.stop()
        fp = ctx.get("floating_icon_process")
        if fp and fp.poll() is None:
            fp.terminate()
        logger.info("Aradhya CLI stopped")


if __name__ == "__main__":
    main()
