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

PROJECT_ROOT = Path(__file__).resolve().parents[2]
IPC_FILE = PROJECT_ROOT / ".aradhya_ipc"
MAX_DIRECT_MODEL_PROMPT_CHARS = 4000


def _render_response(response) -> None:
    # The CLI always shows the transcript echo first so you can see exactly
    # what Aradhya is routing into the planner.
    if response.transcript_echo:
        print(f"Heard > {response.transcript_echo}")
    print(f"Aradhya > {response.spoken_response}")
    print()


def _render_voice_status(
    voice_manager: VoiceInboxManager,
    runtime_profile,
    live_voice_runtime: VoiceActivatedAradhya | None,
) -> None:
    # This is the quickest way to inspect where audio should be dropped and
    # whether Aradhya currently sees any pending files.
    status = voice_manager.status()
    activation_support = describe_voice_activation_support(runtime_profile)
    print(f"Voice > Provider: {status.provider}")
    print(f"Voice > Inbox: {status.inbox_dir}")
    print(f"Voice > Processed: {status.processed_dir}")
    print(f"Voice > Transcripts: {status.transcripts_dir}")
    print(f"Voice > Manual transcripts: {status.manual_transcripts_dir}")
    print(f"Voice > Supported audio: {', '.join(status.supported_extensions)}")
    print(
        "Voice > Whisper command configured: "
        f"{'yes' if status.whisper_command_configured else 'no'}"
    )
    if status.provider == "faster_whisper":
        print(f"Voice > Faster-Whisper model: {status.faster_whisper_model_size}")
        print(f"Voice > Faster-Whisper device: {status.faster_whisper_device}")
        print(f"Voice > Faster-Whisper compute type: {status.faster_whisper_compute_type}")
        print(f"Voice > Faster-Whisper language: {status.language or 'auto'}")
    print(
        "Voice > Live activation available: "
        f"{'yes' if activation_support.available else 'no'}"
    )
    print(
        f"Voice > Live activation running: "
        f"{'yes' if live_voice_runtime and live_voice_runtime.is_running() else 'no'}"
    )
    print(
        "Voice > Live activation hotkey: "
        f"{'+'.join(runtime_profile.voice_activation.hotkey_modifiers).upper()}"
        f"{'+' + runtime_profile.voice_activation.hotkey_key.upper() if runtime_profile.voice_activation.hotkey_key else ''}"
    )
    print(
        "Voice > Spoken replies enabled: "
        f"{'yes' if runtime_profile.voice_output.enabled else 'no'}"
    )
    print(f"Voice > Spoken reply provider: {runtime_profile.voice_output.provider}")
    print(
        "Voice > Spoken reply voice: "
        f"{runtime_profile.voice_output.voice_id or 'system default'}"
    )
    print(f"Voice > Spoken reply rate: {runtime_profile.voice_output.rate}")
    print(f"Voice > Spoken reply volume: {runtime_profile.voice_output.volume}")
    print(f"Voice > Live activation note: {activation_support.message}")
    print(f"Voice > Pending audio files: {len(status.pending_audio)}")
    for pending_audio in status.pending_audio:
        print(f"Voice > Pending: {pending_audio.name}")
    print()


def _render_model_health(model_provider) -> None:
    # This command doubles as a diagnostic scan so the user can see which local
    # models Ollama currently exposes on this machine.
    render_model_health(model_provider.health_check())


def _render_cache_validation(assistant: AradhyaAssistant) -> None:
    report = run_cache_validation(assistant.preferences)
    for line in format_cache_validation_report(report):
        print(line)
    print()


def _sanitize_direct_model_prompt(prompt: str) -> str:
    normalized = " ".join(prompt.split())
    if not normalized:
        raise ValueError("Add a prompt after 'model ask'.")
    if len(normalized) > MAX_DIRECT_MODEL_PROMPT_CHARS:
        raise ValueError(
            "Direct model prompts must stay under "
            f"{MAX_DIRECT_MODEL_PROMPT_CHARS} characters."
        )
    return normalized


def _stop_live_voice_runtime(live_voice_runtime: VoiceActivatedAradhya | None) -> None:
    if live_voice_runtime and live_voice_runtime.is_running():
        live_voice_runtime.stop()


def _process_voice_inbox(
    assistant: AradhyaAssistant,
    voice_manager: VoiceInboxManager,
) -> None:
    # Processing voice is explicit so you can inspect the inbox, transcripts,
    # and archived files while learning how the pipeline behaves.
    results = voice_manager.process_pending_audio()
    if not results:
        print("Voice > No pending audio files were found in the inbox.")
        print()
        return

    for result in results:
        print(f"Voice > {result.message}")
        if result.transcript_path is not None:
            print(f"Voice > Transcript saved to {result.transcript_path}")
        if result.archived_audio_path is not None:
            print(f"Voice > Archived audio to {result.archived_audio_path}")
        if result.transcript_text:
            print(f"Voice > Transcript: {result.transcript_text}")
            if assistant.state.is_awake:
                _render_response(assistant.handle_transcript(result.transcript_text))
            else:
                print(
                    "Aradhya > Transcript saved. Wake Aradhya to route voice into planning."
                )
                print()
        else:
            print()


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
    live_voice_runtime: VoiceActivatedAradhya | None = None
    floating_icon_process: subprocess.Popen | None = None
    wake_word_listener: WakeWordListener | None = None
    # Create the voice folders on startup so the testing workflow is visible in
    # VS Code even before the first audio file is dropped.
    voice_manager.ensure_directories()
    logger.info(
        "Aradhya CLI started with model {} and voice provider {}",
        runtime_profile.model.model_name,
        runtime_profile.voice.provider,
    )

    print("=" * 60)
    print("Aradhya - Personal AI Assistant")
    print("=" * 60)
    print("Type 'wake' or 'ctrl+win' to simulate the wake trigger.")
    print("Type 'voice status', 'voice process', 'voice activate', or 'voice stop'.")
    print("Type 'cache validate' to benchmark the current context cache.")
    print("Type 'model ping' or 'model ask <prompt>' for the configured local model.")
    print("Type 'icon enable' or 'icon disable' to toggle the floating wake icon.")
    print("Type 'wake word enable' or 'wake word disable' to toggle background listening.")
    print("Type 'skills list', 'skills enable <name>', or 'skills disable <name>'.")
    print("Type 'sleep' to send Aradhya idle, or 'exit' to quit.")
    print(f"Configured model > {runtime_profile.model.model_name}")
    print(f"Voice inbox > {runtime_profile.voice.audio_inbox_dir}")
    print(
        f"Skills > {skill_registry.active_count} active / "
        f"{skill_registry.count} loaded"
    )
    print(f"Log file > {log_path}")
    print()

    if runtime_profile.voice_activation.enabled_on_startup:
        try:
            live_voice_runtime = VoiceActivatedAradhya(
                assistant=assistant,
                voice_manager=voice_manager,
                runtime_profile=runtime_profile,
                output_handler=print,
            )
            live_voice_runtime.start()
        except Exception as error:
            print(f"Voice > Live activation auto-start failed: {error}")
            print()

    ipc_thread_running = True

    def ipc_watcher():
        nonlocal live_voice_runtime
        while ipc_thread_running:
            if IPC_FILE.exists():
                try:
                    cmd = IPC_FILE.read_text(encoding="utf-8").strip()
                    IPC_FILE.unlink()
                    if cmd == "wake":
                        print()
                        _render_response(assistant.handle_wake(WakeSource.FLOATING_ICON))
                        print("You > ", end="", flush=True)
                    elif cmd == "sleep":
                        print()
                        _render_response(assistant.go_idle())
                        print("You > ", end="", flush=True)
                    elif cmd == "voice_toggle":
                        print()
                        if live_voice_runtime and live_voice_runtime.is_running():
                            live_voice_runtime.stop()
                        else:
                            if live_voice_runtime is None:
                                live_voice_runtime = VoiceActivatedAradhya(
                                    assistant=assistant,
                                    voice_manager=voice_manager,
                                    runtime_profile=runtime_profile,
                                    output_handler=print,
                                )
                            live_voice_runtime.start()
                        print("\nYou > ", end="", flush=True)
                except Exception:
                    pass
            time.sleep(0.5)

    ipc_thread = threading.Thread(target=ipc_watcher, daemon=True)
    ipc_thread.start()

    try:
        while True:
            try:
                command = input("You > ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                print("Aradhya > Shutting down.")
                break

            normalized = command.lower()

            if normalized == "exit":
                print("Aradhya > Shutting down.")
                break

            if normalized == "sleep":
                _render_response(assistant.go_idle())
                continue

            if normalized == "voice status":
                _render_voice_status(voice_manager, runtime_profile, live_voice_runtime)
                continue

            if normalized == "voice process":
                _process_voice_inbox(assistant, voice_manager)
                continue

            if normalized == "skills list":
                all_skills = skill_registry.all_skills()
                if not all_skills:
                    print("Skills > No skills loaded.")
                else:
                    print(f"Skills > {len(all_skills)} skill(s) loaded:")
                    for skill in all_skills:
                        status = "enabled" if skill.enabled else "disabled"
                        print(f"  [{status}] {skill.name} — {skill.description}")
                print()
                continue

            if normalized.startswith("skills enable "):
                skill_name = command[len("skills enable "):].strip()
                if skill_registry.enable(skill_name):
                    print(f"Skills > Enabled '{skill_name}'.")
                else:
                    print(f"Skills > Skill '{skill_name}' not found.")
                print()
                continue

            if normalized.startswith("skills disable "):
                skill_name = command[len("skills disable "):].strip()
                if skill_registry.disable(skill_name):
                    print(f"Skills > Disabled '{skill_name}'.")
                else:
                    print(f"Skills > Skill '{skill_name}' not found.")
                print()
                continue

            if normalized == "voice activate":
                try:
                    if live_voice_runtime is None:
                        live_voice_runtime = VoiceActivatedAradhya(
                            assistant=assistant,
                            voice_manager=voice_manager,
                            runtime_profile=runtime_profile,
                            output_handler=print,
                        )
                    live_voice_runtime.start()
                except Exception as error:
                    print(f"Voice > Live activation failed: {error}")
                    print()
                continue

            if normalized == "voice stop":
                if live_voice_runtime and live_voice_runtime.is_running():
                    live_voice_runtime.stop()
                else:
                    print("Voice > Live voice activation is not running.")
                    print()
                continue

            if normalized == "wake word enable":
                if wake_word_listener is None:
                    wake_word_listener = WakeWordListener(assistant=assistant, voice_manager=voice_manager)
                wake_word_listener.start()
                print("Voice > Wake word detection enabled (listening for 'wakeup').")
                print()
                continue
                
            if normalized == "wake word disable":
                if wake_word_listener:
                    wake_word_listener.stop()
                print("Voice > Wake word detection disabled.")
                print()
                continue

            if normalized == "model ping":
                _render_model_health(model_provider)
                continue

            if normalized == "icon enable":
                if floating_icon_process is None or floating_icon_process.poll() is not None:
                    try:
                        floating_icon_process = subprocess.Popen(
                            [sys.executable, "-m", "src.aradhya.floating_icon"],
                            cwd=str(PROJECT_ROOT)
                        )
                        print("Icon > Floating icon enabled.")
                    except Exception as error:
                        print(f"Icon > Failed to start floating icon: {error}")
                else:
                    print("Icon > Floating icon is already running.")
                print()
                continue

            if normalized == "icon disable":
                if floating_icon_process and floating_icon_process.poll() is None:
                    floating_icon_process.terminate()
                    floating_icon_process = None
                    print("Icon > Floating icon disabled.")
                else:
                    print("Icon > Floating icon is not running.")
                print()
                continue

            if normalized == "cache validate":
                _render_cache_validation(assistant)
                continue

            if normalized.startswith("model ask "):
                # This command talks to the configured model engine directly and is
                # separate from Aradhya's rule-based planner.
                try:
                    prompt = _sanitize_direct_model_prompt(command[len("model ask ") :])
                except ValueError as error:
                    print(f"Model > {error}")
                    print()
                    continue

                try:
                    result = model_provider.generate(prompt)
                except Exception as error:  # pragma: no cover - defensive CLI path
                    print(f"Model > Generation failed: {error}")
                    print()
                    continue

                print(f"Model > {result.text}")
                print()
                continue

            if normalized in {"wake", "ctrl+win"}:
                source = (
                    WakeSource.HOTKEY if normalized == "ctrl+win" else WakeSource.FLOATING_ICON
                )
                _render_response(assistant.handle_wake(source))
                if runtime_profile.voice.poll_on_wake:
                    # Wake checks the voice inbox so pending files are surfaced
                    # before you manually trigger voice processing.
                    pending_audio = voice_manager.status().pending_audio
                    if pending_audio:
                        print(
                            f"Voice > {len(pending_audio)} pending audio file(s) are waiting in "
                            f"{runtime_profile.voice.audio_inbox_dir}"
                        )
                        print()
                continue

            _render_response(assistant.handle_transcript(command))
    finally:
        ipc_thread_running = False
        if wake_word_listener:
            wake_word_listener.stop()
        _stop_live_voice_runtime(live_voice_runtime)
        if floating_icon_process and floating_icon_process.poll() is None:
            floating_icon_process.terminate()
        logger.info("Aradhya CLI stopped")


if __name__ == "__main__":
    main()
