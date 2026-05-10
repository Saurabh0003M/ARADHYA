"""Optional microphone capture for live voice activation."""

from __future__ import annotations

import queue
import threading
import time
import wave
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable

import numpy as np
from loguru import logger

try:
    import sounddevice as sd

    SOUNDDEVICE_AVAILABLE = True
except ImportError:  # pragma: no cover - depends on optional package
    sd = None
    SOUNDDEVICE_AVAILABLE = False


class AudioBackend(str, Enum):
    """Supported microphone backends."""

    SOUNDDEVICE = "sounddevice"


@dataclass(frozen=True)
class AudioConfig:
    """Microphone tuning values used by the live activation path."""

    sample_rate: int = 16000
    channels: int = 1
    chunk_size: int = 1024
    dtype: str = "int16"
    silence_threshold: float = 0.01
    silence_duration: float = 1.5
    max_recording_duration: float = 30.0


@dataclass(frozen=True)
class RecordingResult:
    """Outcome of a microphone capture attempt."""

    success: bool
    audio_path: Path | None = None
    duration_seconds: float = 0.0
    error_message: str | None = None


class MicrophoneCapture:
    """Capture microphone audio and save it as a WAV file.

    The live voice flow records into Aradhya's existing voice inbox so the same
    transcript writing and archival logic can be reused for both dropped files
    and spoken hotkey captures.
    """

    def __init__(
        self,
        config: AudioConfig | None = None,
        backend: AudioBackend | None = None,
        sounddevice_module: Any | None = None,
    ):
        self.config = config or AudioConfig()
        self.backend = backend or get_available_backend()
        self._sounddevice = sounddevice_module if sounddevice_module is not None else sd
        self._recording = False
        self._frames: list[np.ndarray] = []
        self._audio_queue: queue.Queue[np.ndarray] = queue.Queue()
        self._record_thread: threading.Thread | None = None

        if self.backend is None:
            raise RuntimeError(
                "No live audio backend is available. Install requirements-voice-activation.txt."
            )
        if self.backend == AudioBackend.SOUNDDEVICE and not SOUNDDEVICE_AVAILABLE:
            raise RuntimeError(
                "The sounddevice backend is not available. "
                "Install requirements-voice-activation.txt."
            )

    def is_recording(self) -> bool:
        """Return whether audio capture is currently active."""

        return self._recording

    def cancel_recording(self) -> None:
        """Stop an in-flight recording without saving a new file."""

        self._recording = False
        if self._record_thread and self._record_thread.is_alive():
            self._record_thread.join(timeout=2.0)

    def record_until_silence(
        self,
        output_path: Path,
        on_speaking_started: Callable[[], None] | None = None,
    ) -> RecordingResult:
        """Record until speech ends or the maximum duration is reached."""

        self._start_recording()
        silence_frame_limit = int(
            self.config.silence_duration * self.config.sample_rate / self.config.chunk_size
        )
        max_frame_limit = int(
            self.config.max_recording_duration * self.config.sample_rate / self.config.chunk_size
        )
        speaking_detected = False
        silence_frames = 0
        captured_frames = 0

        try:
            while self._recording and captured_frames < max_frame_limit:
                try:
                    chunk = self._audio_queue.get(timeout=0.1)
                except queue.Empty:
                    continue

                captured_frames += 1
                amplitude = np.abs(chunk.astype(np.float32)).mean() / max(np.iinfo(np.int16).max, 1)
                if amplitude > self.config.silence_threshold:
                    silence_frames = 0
                    if not speaking_detected:
                        speaking_detected = True
                        if on_speaking_started is not None:
                            on_speaking_started()
                        logger.debug("Detected spoken audio during live capture")
                elif speaking_detected:
                    silence_frames += 1

                if speaking_detected and silence_frames >= silence_frame_limit:
                    logger.debug("Silence threshold reached; stopping live capture")
                    break

            return self._stop_recording(output_path)
        except Exception as error:
            self.cancel_recording()
            return RecordingResult(
                success=False,
                error_message=f"Live recording failed: {error}",
            )

    def _start_recording(self) -> None:
        if self._recording:
            raise RuntimeError("A recording is already in progress.")

        self._recording = True
        self._frames = []
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except queue.Empty:
                break

        self._record_thread = threading.Thread(
            target=self._run_sounddevice_stream,
            daemon=True,
        )
        self._record_thread.start()
        logger.info("Started live microphone capture")

    def _stop_recording(self, output_path: Path) -> RecordingResult:
        self._recording = False
        if self._record_thread and self._record_thread.is_alive():
            self._record_thread.join(timeout=2.0)

        if not self._frames:
            return RecordingResult(
                success=False,
                error_message="No audio data was captured from the microphone.",
            )

        audio_data = np.concatenate(self._frames).astype(np.int16)
        duration_seconds = len(audio_data) / self.config.sample_rate
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with wave.open(str(output_path), "wb") as audio_file:
            audio_file.setnchannels(self.config.channels)
            audio_file.setsampwidth(2)
            audio_file.setframerate(self.config.sample_rate)
            audio_file.writeframes(audio_data.tobytes())

        logger.info("Saved live microphone capture to {}", output_path)
        return RecordingResult(
            success=True,
            audio_path=output_path,
            duration_seconds=duration_seconds,
        )

    def _run_sounddevice_stream(self) -> None:
        if self._sounddevice is None:
            raise RuntimeError("sounddevice is not available.")

        def callback(indata, _frames, _time, status) -> None:
            if status:
                logger.warning("sounddevice reported status {}", status)
            if not self._recording:
                return

            chunk = np.asarray(indata).reshape(-1).copy()
            self._frames.append(chunk)
            self._audio_queue.put(chunk)

        with self._sounddevice.InputStream(
            samplerate=self.config.sample_rate,
            channels=self.config.channels,
            dtype=self.config.dtype,
            blocksize=self.config.chunk_size,
            callback=callback,
        ):
            while self._recording:
                time.sleep(0.05)


def get_available_backend(preferred_backend: str | None = None) -> AudioBackend | None:
    """Return the best available backend for live capture."""

    normalized_preference = (preferred_backend or "").strip().lower()
    if normalized_preference and normalized_preference != AudioBackend.SOUNDDEVICE.value:
        logger.warning(
            "Unsupported audio backend preference '{}'; falling back to sounddevice.",
            preferred_backend,
        )

    if SOUNDDEVICE_AVAILABLE:
        return AudioBackend.SOUNDDEVICE
    return None
