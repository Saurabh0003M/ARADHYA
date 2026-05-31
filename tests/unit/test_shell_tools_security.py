import sys
from unittest.mock import MagicMock

# Mock dependencies
sys.modules['loguru'] = MagicMock()
sys.modules['rich'] = MagicMock()
sys.modules['rich.console'] = MagicMock()
sys.modules['requests'] = MagicMock()
sys.modules['mcp'] = MagicMock()
sys.modules['mcp.client'] = MagicMock()
sys.modules['mcp.client.stdio'] = MagicMock()
sys.modules['mcp.client.session'] = MagicMock()
sys.modules['mcp.types'] = MagicMock()
sys.modules['vlc'] = MagicMock()
sys.modules['numpy'] = MagicMock()
sys.modules['sounddevice'] = MagicMock()
sys.modules['yaml'] = MagicMock()
sys.modules['selenium'] = MagicMock()
sys.modules['openai'] = MagicMock()
sys.modules['playwright'] = MagicMock()

import pytest
from src.aradhya.tools.shell_tools import run_command

def test_run_command_prevents_injection():
    """Test that run_command properly prevents shell injection using shell=False."""
    # With shell=False and shlex.split, "echo hello; echo injected"
    # becomes ['echo', 'hello;', 'echo', 'injected']
    # So "hello;" "echo" "injected" will all be printed literally by echo.

    command = "echo hello; echo injected"
    result = run_command(command=command)

    # It should print them out as literals, meaning exit code is 0 but they are printed by echo
    # STDOUT should be "hello; echo injected"
    assert "Exit code: 0" in result
    assert "hello; echo injected" in result

    command = "echo hello && echo injected"
    result = run_command(command=command)
    assert "Exit code: 0" in result
    assert "hello && echo injected" in result

    command = "echo hello | grep h"
    result = run_command(command=command)
    assert "Exit code: 0" in result
    assert "hello | grep h" in result

    command = "echo hello > test_file.txt"
    result = run_command(command=command)
    assert "Exit code: 0" in result
    assert "hello > test_file.txt" in result

from src.aradhya.hooks.hook_engine import HookEngine, HookDefinition, HookEvent, HookType
from src.aradhya.voice.transcriber import WhisperCommandFileTranscriber
from pathlib import Path
from dataclasses import replace

def test_hook_engine_command_hook_injection():
    """Test that command hooks don't evaluate shell features."""
    engine = HookEngine()

    hook = HookDefinition(
        event=HookEvent.PRE_TOOL_USE,
        hook_type=HookType.COMMAND,
        command="echo foo; echo bar"
    )
    result = engine._run_command_hook(hook.command, {"test": "data"}, timeout=5)

    assert result == {}

def test_whisper_command_injection(tmp_path):
    """Test that WhisperCommandFileTranscriber doesn't evaluate shell features."""
    from src.aradhya.runtime_profile import load_runtime_profile
    import os
    os.environ['ARADHYA_HOME'] = str(tmp_path)

    profile = load_runtime_profile()

    # We create a new VoiceProfile with the needed fields modified. It's usually a dataclass.
    vp = replace(
        profile.voice,
        provider="whisper_command",
        whisper_command_template="echo {audio_path} ; echo {transcript_path}"
    )

    transcriber = WhisperCommandFileTranscriber(vp)
    audio = tmp_path / "test.wav"
    transcript = tmp_path / "test.txt"

    result = transcriber.transcribe(audio, transcript)

    # With shell=False, echo prints the literals
    assert ";" in result.transcript_text
    assert "echo" in result.transcript_text
