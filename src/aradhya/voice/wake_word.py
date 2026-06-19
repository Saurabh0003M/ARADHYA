"""Background wake word listener using continuous audio chunk capture."""

import threading
import time
from pathlib import Path

from loguru import logger

from src.aradhya.voice.microphone import MicrophoneCapture, AudioConfig, get_available_backend
from src.aradhya.voice.pipeline import VoiceInboxManager
from src.aradhya.assistant_core import AradhyaAssistant
from src.aradhya.assistant_models import WakeSource


class WakeWordListener:
    WAKE_WORDS = ("wakeup", "wake up", "arise")

    def __init__(self, assistant: AradhyaAssistant, voice_manager: VoiceInboxManager):
        self.assistant = assistant
        self.voice_manager = voice_manager
        self.running = False
        self._thread = None
        self._lock = threading.Lock()

        # We'll use smaller chunks and duration for the wake word
        # 2 seconds max duration to keep it snappy.
        self.mic = MicrophoneCapture(
            config=AudioConfig(
                max_recording_duration=2.5,
                silence_duration=0.5,
                silence_threshold=0.015,
            ),
            backend=get_available_backend()
        )

    def start(self):
        with self._lock:
            if self.running:
                return
            self.running = True
            self._thread = threading.Thread(target=self._listen_loop, daemon=True)
            self._thread.start()
            logger.info("Wake word listener started.")

    def stop(self):
        with self._lock:
            self.running = False
            if self.mic.is_recording():
                self.mic.cancel_recording()
            logger.info("Wake word listener stopped.")

    def _listen_loop(self):
        while self.running:
            # If Aradhya is already awake, don't spam recordings
            if self.assistant.state.is_awake:
                time.sleep(1.0)
                continue

            temp_path = self.voice_manager.profile.audio_inbox_dir / "temp_wakeword.wav"

            # This blocks until 2.5s is up or silence is detected
            result = self.mic.record_until_silence(temp_path)

            if not self.running:
                break

            if result.success and result.audio_path:
                self._handle_audio_chunk(result.audio_path)

            time.sleep(0.1)

    def _handle_audio_chunk(self, audio_path: Path) -> bool:
        """Transcribe one captured chunk and trigger wake on a match.

        Returns ``True`` when a wake word was detected. Temporary audio and
        transcript files are always cleaned up, so the inbox stays empty even
        when transcription fails.
        """

        # Keep the throwaway transcript next to the temp audio so a single
        # cleanup pass removes both regardless of which provider wrote it.
        transcript_destination = audio_path.with_suffix(".wake.txt")
        detected = False
        try:
            transcription = self.voice_manager.transcribe_audio(
                audio_path, transcript_destination
            )
            normalized = (transcription.transcript_text or "").lower().strip()

            if normalized and any(w in normalized for w in self.WAKE_WORDS):
                logger.info(f"Wake word detected in transcript: {normalized}")
                print("\nVoice > Wake word detected!")
                # Trigger the wake action
                wake_response = self.assistant.handle_wake(WakeSource.VOICE)
                print(f"Aradhya > {wake_response.spoken_response}")
                print("You > ", end="", flush=True)  # Reprompt input cleanly
                detected = True
        except Exception as e:
            logger.debug(f"Wake word transcription failed: {e}")
        finally:
            # Clean up the temp audio and transcript files
            for cleanup_path in (audio_path, transcript_destination):
                try:
                    if cleanup_path.exists():
                        cleanup_path.unlink()
                except OSError:
                    pass

        return detected
