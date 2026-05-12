from pathlib import Path
from unittest.mock import patch, MagicMock

from src.aradhya.voice.transcriber import WhisperCommandFileTranscriber

def test_whisper_command_prevents_injection():
    # Setup profile mock with whisper_command
    profile = MagicMock()
    profile.provider = "whisper_command"
    profile.whisper_command_template = "whisper {audio_path} --output {transcript_path}"

    transcriber = WhisperCommandFileTranscriber(profile)

    audio_path = Path("test audio; rm -rf /.wav")
    transcript_dest = Path("output transcript; touch pwned.txt")

    with patch("src.aradhya.voice.transcriber.subprocess.run") as mock_run:
        transcriber.transcribe(audio_path, transcript_dest)

        # Check that the rendered command is safely quoted
        mock_run.assert_called_once()
        rendered_command = mock_run.call_args[0][0]

        # shlex.quote handles spaces and quotes characters so we shouldn't see bare malicious payload
        assert "rm -rf" in rendered_command
        assert "'" in rendered_command # verify it got quoted

        # Print for debugging
        print(f"Rendered command: {rendered_command}")

        # It should look something like:
        # whisper 'test audio; rm -rf /.wav' --output 'output transcript; touch pwned.txt'
