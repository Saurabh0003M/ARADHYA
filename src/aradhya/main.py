"""Interactive CLI entry point for the Aradhya assistant core."""

from __future__ import annotations

from pathlib import Path

from src.aradhya.assistant_core import AradhyaAssistant
from src.aradhya.assistant_models import WakeSource
from src.aradhya.model_provider import build_text_model_provider
from src.aradhya.runtime_profile import load_runtime_profile
from src.aradhya.voice_pipeline import VoiceInboxManager

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _render_response(response) -> None:
    if response.transcript_echo:
        print(f"Heard > {response.transcript_echo}")
    print(f"Aradhya > {response.spoken_response}")
    print()


def _render_voice_status(voice_manager: VoiceInboxManager) -> None:
    status = voice_manager.status()
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
    print(f"Voice > Pending audio files: {len(status.pending_audio)}")
    for pending_audio in status.pending_audio:
        print(f"Voice > Pending: {pending_audio.name}")
    print()


def _render_model_health(model_provider) -> None:
    health = model_provider.health_check()
    print(f"Model > Provider: {health.provider}")
    print(f"Model > Configured model: {health.configured_model}")
    print(f"Model > Reachable: {'yes' if health.reachable else 'no'}")
    print(f"Model > Ready: {'yes' if health.ready else 'no'}")
    if health.available_models:
        print(f"Model > Available: {', '.join(health.available_models)}")
    print(f"Model > {health.message}")
    print()


def _process_voice_inbox(
    assistant: AradhyaAssistant,
    voice_manager: VoiceInboxManager,
) -> None:
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
    assistant = AradhyaAssistant.from_project_root(PROJECT_ROOT)
    runtime_profile = load_runtime_profile(PROJECT_ROOT)
    voice_manager = VoiceInboxManager(runtime_profile.voice)
    voice_manager.ensure_directories()
    model_provider = build_text_model_provider(runtime_profile.model)

    print("=" * 60)
    print("Aradhya - Personal AI Assistant")
    print("=" * 60)
    print("Type 'wake' or 'ctrl+win' to simulate the wake trigger.")
    print("Type 'voice status' or 'voice process' for the audio inbox flow.")
    print("Type 'model ping' or 'model ask <prompt>' for the configured local model.")
    print("Type 'sleep' to send Aradhya idle, or 'exit' to quit.")
    print(f"Configured model > {runtime_profile.model.model_name}")
    print(f"Voice inbox > {runtime_profile.voice.audio_inbox_dir}")
    print()

    while True:
        command = input("You > ").strip()
        normalized = command.lower()

        if normalized == "exit":
            print("Aradhya > Shutting down.")
            break

        if normalized == "sleep":
            _render_response(assistant.go_idle())
            continue

        if normalized == "voice status":
            _render_voice_status(voice_manager)
            continue

        if normalized == "voice process":
            _process_voice_inbox(assistant, voice_manager)
            continue

        if normalized == "model ping":
            _render_model_health(model_provider)
            continue

        if normalized.startswith("model ask "):
            prompt = command[len("model ask ") :].strip()
            if not prompt:
                print("Model > Add a prompt after 'model ask'.")
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
                pending_audio = voice_manager.status().pending_audio
                if pending_audio:
                    print(
                        f"Voice > {len(pending_audio)} pending audio file(s) are waiting in "
                        f"{runtime_profile.voice.audio_inbox_dir}"
                    )
                    print()
            continue

        _render_response(assistant.handle_transcript(command))


if __name__ == "__main__":
    main()
