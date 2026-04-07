"""Live voice activation built on Aradhya's existing planner and voice inbox."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import threading
from typing import Callable

from loguru import logger

from src.aradhya.assistant_core import AradhyaAssistant
from src.aradhya.assistant_models import WakeSource
from src.aradhya.hotkey_listener import HotkeyListener, build_hotkey_config
from src.aradhya.logging_utils import configure_logging
from src.aradhya.microphone_capture import AudioConfig, MicrophoneCapture, get_available_backend
from src.aradhya.model_provider import build_text_model_provider
from src.aradhya.runtime_profile import RuntimeProfile, load_runtime_profile
from src.aradhya.voice_pipeline import VoiceInboxManager, VoiceJobResult


@dataclass(frozen=True)
class VoiceActivationSupport:
    """Availability report for live voice activation."""

    available: bool
    message: str


class VoiceActivatedAradhya:
    """Background hotkey listener that captures speech and routes it into Aradhya.

    This class deliberately reuses ``VoiceInboxManager.process_audio_file`` so
    live recordings and dropped audio files follow the same transcription,
    transcript-writing, and archival path.
    """

    def __init__(
        self,
        assistant: AradhyaAssistant,
        voice_manager: VoiceInboxManager,
        runtime_profile: RuntimeProfile,
        output_handler: Callable[[str], None] | None = None,
        microphone: MicrophoneCapture | None = None,
        hotkey_listener: HotkeyListener | None = None,
    ):
        if runtime_profile.voice.provider not in {"faster_whisper", "whisper_command"}:
            raise RuntimeError(
                "Live voice activation requires voice.provider to be "
                "'faster_whisper' or 'whisper_command'."
            )

        if microphone is None or hotkey_listener is None:
            support = describe_voice_activation_support(runtime_profile)
            if not support.available:
                raise RuntimeError(support.message)

        self.assistant = assistant
        self.voice_manager = voice_manager
        self.runtime_profile = runtime_profile
        self.output_handler = output_handler or print
        self._activation_lock = threading.Lock()
        self._running = False
        self._capture_counter = 0
        self.microphone = microphone or MicrophoneCapture(
            config=AudioConfig(
                sample_rate=runtime_profile.voice_activation.sample_rate,
                channels=runtime_profile.voice_activation.channels,
                chunk_size=runtime_profile.voice_activation.chunk_size,
                silence_threshold=runtime_profile.voice_activation.silence_threshold,
                silence_duration=runtime_profile.voice_activation.silence_duration,
                max_recording_duration=runtime_profile.voice_activation.max_recording_duration,
            ),
            backend=get_available_backend(runtime_profile.voice_activation.preferred_backend),
        )
        self.hotkey_listener = hotkey_listener or HotkeyListener(
            build_hotkey_config(
                runtime_profile.voice_activation.hotkey_modifiers,
                runtime_profile.voice_activation.hotkey_key,
            ),
            self._handle_hotkey_press,
        )

    def start(self) -> None:
        """Start listening for the configured wake hotkey."""

        if self._running:
            self.output_handler("Voice > Live voice activation is already running.")
            return

        self._running = True
        self.voice_manager.ensure_directories()
        try:
            self.hotkey_listener.start()
        except Exception:
            self._running = False
            raise
        hotkey_description = build_hotkey_config(
            self.runtime_profile.voice_activation.hotkey_modifiers,
            self.runtime_profile.voice_activation.hotkey_key,
        ).describe()
        logger.info("Started live voice activation with hotkey {}", hotkey_description)
        self.output_handler(
            f"Voice > Live voice activation is running. Press {hotkey_description} to speak."
        )

    def stop(self) -> None:
        """Stop listening for the live voice hotkey."""

        if not self._running:
            return

        self._running = False
        self.hotkey_listener.stop()
        if self.microphone.is_recording():
            self.microphone.cancel_recording()
        logger.info("Stopped live voice activation")
        self.output_handler("Voice > Live voice activation stopped.")

    def is_running(self) -> bool:
        """Return whether live voice activation is currently active."""

        return self._running

    def _handle_hotkey_press(self) -> None:
        if not self._running:
            return
        if not self._activation_lock.acquire(blocking=False):
            logger.info("Ignored overlapping hotkey press while live capture was active")
            return

        try:
            if not self.assistant.state.is_awake:
                wake_response = self.assistant.handle_wake(WakeSource.HOTKEY)
                self.output_handler(f"Aradhya > {wake_response.spoken_response}")

            capture_path = self._next_capture_path()
            self.output_handler("Voice > Recording started. Speak now.")
            recording = self.microphone.record_until_silence(
                capture_path,
                on_speaking_started=lambda: logger.debug("Speech detected in live activation"),
            )

            if not recording.success or recording.audio_path is None:
                self.output_handler(
                    f"Voice > Recording failed: {recording.error_message or 'Unknown error.'}"
                )
                return

            voice_job = self.voice_manager.process_audio_file(recording.audio_path)
            self._render_voice_job(voice_job)
            if not voice_job.transcript_text:
                return

            self.output_handler(f"Heard > {voice_job.transcript_text}")
            response = self.assistant.handle_transcript(voice_job.transcript_text)
            self.output_handler(f"Aradhya > {response.spoken_response}")
            if response.awaiting_confirmation:
                self.output_handler(
                    "Voice > Say 'yes proceed' or 'cancel' with the hotkey or the CLI."
                )
        finally:
            self._activation_lock.release()

    def _next_capture_path(self) -> Path:
        self._capture_counter += 1
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"live_capture_{timestamp}_{self._capture_counter:04d}.wav"
        return self.voice_manager.profile.audio_inbox_dir / filename

    def _render_voice_job(self, voice_job: VoiceJobResult) -> None:
        self.output_handler(f"Voice > {voice_job.message}")
        if voice_job.transcript_path is not None:
            self.output_handler(f"Voice > Transcript saved to {voice_job.transcript_path}")
        if voice_job.archived_audio_path is not None:
            self.output_handler(f"Voice > Archived audio to {voice_job.archived_audio_path}")


def describe_voice_activation_support(runtime_profile: RuntimeProfile) -> VoiceActivationSupport:
    """Return whether live voice activation can run on the current machine."""

    if runtime_profile.voice.provider not in {"faster_whisper", "whisper_command"}:
        return VoiceActivationSupport(
            available=False,
            message=(
                "Live voice activation requires a self-transcribing voice provider. "
                "Set voice.provider to 'faster_whisper' or 'whisper_command' in profile.json."
            ),
        )

    if get_available_backend(runtime_profile.voice_activation.preferred_backend) is None:
        return VoiceActivationSupport(
            available=False,
            message=(
                "No supported microphone backend is available. Install "
                "requirements-voice-activation.txt."
            ),
        )

    try:
        build_hotkey_config(
            runtime_profile.voice_activation.hotkey_modifiers,
            runtime_profile.voice_activation.hotkey_key,
        )
    except ValueError as error:
        return VoiceActivationSupport(
            available=False,
            message=f"Invalid voice activation hotkey configuration: {error}",
        )

    try:
        HotkeyListener(
            build_hotkey_config(
                runtime_profile.voice_activation.hotkey_modifiers,
                runtime_profile.voice_activation.hotkey_key,
            ),
            lambda: None,
        )
    except RuntimeError as error:
        return VoiceActivationSupport(available=False, message=str(error))

    return VoiceActivationSupport(
        available=True,
        message="Live voice activation is available on this machine.",
    )


def create_voice_activated_aradhya(
    project_root: Path | None = None,
    output_handler: Callable[[str], None] | None = None,
) -> VoiceActivatedAradhya:
    """Create a live voice activation runtime using the current project config."""

    runtime_profile = load_runtime_profile(project_root)
    model_provider = build_text_model_provider(runtime_profile.model)
    assistant = AradhyaAssistant.from_project_root(
        project_root=project_root,
        model_provider=model_provider,
    )
    voice_manager = VoiceInboxManager(runtime_profile.voice)
    return VoiceActivatedAradhya(
        assistant=assistant,
        voice_manager=voice_manager,
        runtime_profile=runtime_profile,
        output_handler=output_handler,
    )


def main() -> None:
    """Standalone entry point for live voice activation tests."""

    project_root = Path(__file__).resolve().parents[2]
    configure_logging(project_root)
    voice_runtime = create_voice_activated_aradhya(
        project_root=project_root,
        output_handler=print,
    )
    voice_runtime.start()

    try:
        while True:
            threading.Event().wait(0.1)
    except KeyboardInterrupt:
        voice_runtime.stop()


if __name__ == "__main__":
    main()
