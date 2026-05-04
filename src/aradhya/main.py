"""Interactive CLI entry point for the Aradhya assistant core."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import threading
import time

from loguru import logger

from src.aradhya.assistant_core import AradhyaAssistant
from src.aradhya.assistant_models import WakeSource
from src.aradhya.cache_diagnostics import (
    format_cache_validation_report,
    run_cache_validation,
)
from src.aradhya.cli_ui import (
    console,
    render_banner,
    render_error,
    render_health_check,
    render_help,
    render_info,
    render_response,
    render_skills_list,
    render_status,
    render_success,
    render_voice_status,
    render_warning,
    prompt_input,
)
from src.aradhya.logging_utils import configure_logging
from src.aradhya.model_setup import bootstrap_runtime_profile, render_model_health
from src.aradhya.model_provider import build_text_model_provider
from src.aradhya.runtime_profile import load_runtime_profile
from src.aradhya.skills import load_skills
from src.aradhya.voice_activation import (
    VoiceActivatedAradhya,
    describe_voice_activation_support,
)
from src.aradhya.voice_pipeline import VoiceInboxManager
from src.aradhya.wake_word_listener import WakeWordListener
from src.aradhya.audit_logger import get_audit_logger

PROJECT_ROOT = Path(__file__).resolve().parents[2]
IPC_FILE = PROJECT_ROOT / ".aradhya_ipc"
MAX_DIRECT_MODEL_PROMPT_CHARS = 4000


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
        f"{v.major}.{v.minor}.{v.micro}" + ("" if ok else " — need 3.10+"),
    ))

    # 2. Ollama reachability + model
    try:
        health = model_provider.health_check()
        model_ok = getattr(health, "reachable", False)
        model_name = runtime_profile.model.model_name
        if model_ok:
            checks.append(("Ollama", True, f"Connected — {model_name}"))
        else:
            msg = getattr(health, "error", "unreachable")
            checks.append(("Ollama", False, f"Offline — {msg}"))
    except Exception as exc:
        checks.append(("Ollama", False, f"Error — {exc}"))

    # 3. Config files
    prefs_path = PROJECT_ROOT / "core" / "memory" / "preferences.json"
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

def _handle_help(**_) -> None:
    render_help()


def _handle_status(*, assistant, runtime_profile, model_provider,
                   live_voice_runtime, **_) -> None:
    model_ok = None
    try:
        health = model_provider.health_check()
        model_ok = getattr(health, "reachable", False)
    except Exception:
        model_ok = False

    render_status(
        is_awake=assistant.state.is_awake,
        model_name=runtime_profile.model.model_name,
        model_ok=model_ok,
        pending_plan=assistant.state.pending_plan,
        voice_provider=runtime_profile.voice.provider,
        voice_running=bool(live_voice_runtime and live_voice_runtime.is_running()),
        skills_active=assistant.skill_registry.active_count if assistant.skill_registry else 0,
        skills_total=assistant.skill_registry.count if assistant.skill_registry else 0,
        live_execution=assistant.preferences.allow_live_execution,
    )


def _handle_sleep(*, assistant, **_) -> None:
    resp = assistant.go_idle()
    render_response(resp.spoken_response)


def _handle_voice_status(*, voice_manager, runtime_profile,
                         live_voice_runtime, **_) -> None:
    status = voice_manager.status()
    activation_support = describe_voice_activation_support(runtime_profile)
    render_voice_status(
        status, activation_support, runtime_profile,
        bool(live_voice_runtime and live_voice_runtime.is_running()),
    )


def _handle_voice_process(*, assistant, voice_manager, **_) -> None:
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
                           ctx, **_) -> None:
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


def _handle_voice_stop(*, ctx, **_) -> None:
    lvr = ctx.get("live_voice_runtime")
    if lvr and lvr.is_running():
        lvr.stop()
    else:
        render_info("Live voice activation is not running.")


def _handle_wake_word_on(*, assistant, voice_manager, ctx, **_) -> None:
    if ctx.get("wake_word_listener") is None:
        ctx["wake_word_listener"] = WakeWordListener(
            assistant=assistant, voice_manager=voice_manager,
        )
    ctx["wake_word_listener"].start()
    render_success("Wake word detection enabled (listening for 'wakeup').")


def _handle_wake_word_off(*, ctx, **_) -> None:
    wl = ctx.get("wake_word_listener")
    if wl:
        wl.stop()
    render_success("Wake word detection disabled.")


def _handle_model_ping(*, model_provider, **_) -> None:
    render_model_health(model_provider.health_check())


def _handle_model_ask(*, command, model_provider, **_) -> None:
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
    try:
        result = model_provider.generate(normalized)
        console.print(f"  [accent]Model ›[/] {result.text}")
        console.print()
    except Exception as error:
        render_error(f"Generation failed: {error}")


def _handle_skills_list(*, skill_registry, **_) -> None:
    all_skills = skill_registry.all_skills() if skill_registry else []
    render_skills_list(all_skills)


def _handle_skills_enable(*, command, skill_registry, **_) -> None:
    name = command.split(maxsplit=2)[-1].strip() if len(command.split()) > 2 else ""
    if not name:
        render_error("Usage: /skills enable <name>")
        return
    if skill_registry and skill_registry.enable(name):
        render_success(f"Enabled '{name}'.")
    else:
        render_error(f"Skill '{name}' not found.")


def _handle_skills_disable(*, command, skill_registry, **_) -> None:
    name = command.split(maxsplit=2)[-1].strip() if len(command.split()) > 2 else ""
    if not name:
        render_error("Usage: /skills disable <name>")
        return
    if skill_registry and skill_registry.disable(name):
        render_success(f"Disabled '{name}'.")
    else:
        render_error(f"Skill '{name}' not found.")


def _handle_icon_on(*, ctx, **_) -> None:
    fp = ctx.get("floating_icon_process")
    if fp is None or fp.poll() is not None:
        try:
            ctx["floating_icon_process"] = subprocess.Popen(
                [sys.executable, "-m", "src.aradhya.floating_icon"],
                cwd=str(PROJECT_ROOT),
            )
            render_success("Floating icon enabled.")
        except Exception as error:
            render_error(f"Failed to start floating icon: {error}")
    else:
        render_info("Floating icon is already running.")


def _handle_icon_off(*, ctx, **_) -> None:
    fp = ctx.get("floating_icon_process")
    if fp and fp.poll() is None:
        fp.terminate()
        ctx["floating_icon_process"] = None
        render_success("Floating icon disabled.")
    else:
        render_info("Floating icon is not running.")


def _handle_cache(*, assistant, **_) -> None:
    report = run_cache_validation(assistant.preferences)
    for line in format_cache_validation_report(report):
        console.print(f"  {line}")
    console.print()


def _handle_telegram_start(*, assistant, ctx, **_) -> None:
    if ctx.get("telegram_bot") and ctx["telegram_bot"].is_running():
        render_info("Telegram bot is already running.")
        return
    try:
        from src.aradhya.telegram_bot import AradhyaTelegramBot, _load_telegram_config
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


def _handle_telegram_stop(*, ctx, **_) -> None:
    bot = ctx.get("telegram_bot")
    if bot and bot.is_running():
        bot.stop()
        ctx["telegram_bot"] = None
        render_success("Telegram bot stopped.")
    else:
        render_info("Telegram bot is not running.")


def _handle_audit(**_) -> None:
    audit = get_audit_logger()
    entries = audit.recent_entries(15)
    if not entries:
        render_info("No audit entries yet.")
        return
    console.print("[heading]  Recent Audit Log[/]")
    for entry in entries:
        ts = entry.get("ts", "?")[-8:]  # just the time part
        etype = entry.get("type", "?")
        if etype == "tool_call":
            tool = entry.get("tool", "?")
            ok = "OK" if entry.get("success") else "FAIL"
            console.print(f"  [dim]{ts}[/] [accent]{tool}[/] [{ok}]")
        elif etype == "command":
            cmd = entry.get("command", "?")
            console.print(f"  [dim]{ts}[/] cmd: {cmd}")
        elif etype == "security":
            evt = entry.get("event", "?")
            console.print(f"  [dim]{ts}[/] [warning]SECURITY: {evt}[/]")
        else:
            console.print(f"  [dim]{ts}[/] {etype}")
    console.print()


def _handle_daemon_start(*, ctx, **_) -> None:
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
        render_success(
            f"Daemon started in background (PID: {ctx['daemon_process'].pid}). "
            "API on http://127.0.0.1:19842"
        )
    except Exception as error:
        render_error(f"Failed to start daemon: {error}")


def _handle_daemon_stop(*, ctx, **_) -> None:
    dp = ctx.get("daemon_process")
    if dp and dp.poll() is None:
        dp.terminate()
        ctx["daemon_process"] = None
        render_success("Daemon stopped.")
    else:
        render_info("Daemon is not running from this session.")


def _handle_setup(**_) -> None:
    try:
        from src.aradhya.setup_wizard import run_wizard
        run_wizard()
    except Exception as error:
        render_error(f"Setup wizard failed: {error}")


# ── Command dispatch ──────────────────────────────────────────────────

# Maps slash commands and their legacy equivalents to handlers.
# The dispatch logic tries longest match first so "/voice process"
# beats "/voice".

COMMAND_TABLE: list[tuple[list[str], callable]] = [
    # Core
    (["/help", "help"], _handle_help),
    (["/status"], _handle_status),
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
                handler(command=command, **kwargs)
                return True
    return False


# ── IPC watcher ───────────────────────────────────────────────────────

def _start_ipc_watcher(assistant, voice_manager, runtime_profile, ctx):
    """Background thread that reads commands from the floating icon."""
    running = True

    def watcher():
        while ctx.get("ipc_running", True):
            if IPC_FILE.exists():
                try:
                    cmd = IPC_FILE.read_text(encoding="utf-8").strip()
                    IPC_FILE.unlink()
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
                except Exception:
                    pass
            time.sleep(0.5)

    t = threading.Thread(target=watcher, daemon=True)
    t.start()
    return t


# ── Main entry point ──────────────────────────────────────────────────

def main() -> None:
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

    # ── Shared kwargs for all command handlers ────────────────────────
    handler_kwargs = dict(
        assistant=assistant,
        model_provider=model_provider,
        runtime_profile=runtime_profile,
        voice_manager=voice_manager,
        skill_registry=skill_registry,
        live_voice_runtime=ctx.get("live_voice_runtime"),
        ctx=ctx,
    )

    # ── Main input loop ───────────────────────────────────────────────
    try:
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
            resp = assistant.handle_transcript(command)
            render_response(
                resp.spoken_response,
                transcript_echo=resp.transcript_echo,
                awaiting=resp.awaiting_confirmation,
            )

    finally:
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
