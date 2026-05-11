import sys
from unittest.mock import MagicMock

# Mock dependencies before any other imports
sys.modules["loguru"] = MagicMock()
sys.modules["requests"] = MagicMock()
sys.modules["vlc"] = MagicMock()
sys.modules["pvporcupine"] = MagicMock()
sys.modules["pyaudio"] = MagicMock()
sys.modules["pveagle"] = MagicMock()
sys.modules["yaml"] = MagicMock()
sys.modules["dotenv"] = MagicMock()
sys.modules["openai"] = MagicMock()

import json
import os
from pathlib import Path
from src.aradhya.audit_logger import _sanitize_args, AuditLogger

def test_sanitize_args_redaction():
    # Exact matches
    assert _sanitize_args({"password": "secret123"}) == {"password": "***REDACTED***"}
    assert _sanitize_args({"token": "abc-123"}) == {"token": "***REDACTED***"}
    assert _sanitize_args({"secret": "my-secret"}) == {"secret": "***REDACTED***"}
    assert _sanitize_args({"api_key": "key-456"}) == {"api_key": "***REDACTED***"}
    assert _sanitize_args({"key": "some-key"}) == {"key": "***REDACTED***"}
    assert _sanitize_args({"credential": "user-pass"}) == {"credential": "***REDACTED***"}

def test_sanitize_args_case_insensitivity():
    assert _sanitize_args({"PASSWORD": "123"}) == {"PASSWORD": "***REDACTED***"}
    assert _sanitize_args({"Api_Key": "456"}) == {"Api_Key": "***REDACTED***"}

def test_sanitize_args_partial_matches():
    assert _sanitize_args({"user_password": "123"}) == {"user_password": "***REDACTED***"}
    assert _sanitize_args({"github_token": "abc"}) == {"github_token": "***REDACTED***"}
    assert _sanitize_args({"secret_manager": "xyz"}) == {"secret_manager": "***REDACTED***"}

def test_sanitize_args_truncation():
    long_val = "a" * 600
    expected = "a" * 500 + "...[truncated]"
    assert _sanitize_args({"output": long_val}) == {"output": expected}

def test_sanitize_args_preservation():
    short_val = "hello world"
    assert _sanitize_args({"message": short_val}) == {"message": short_val}
    assert _sanitize_args({"count": 42}) == {"count": 42}

def test_audit_logger_initialization(tmp_path):
    audit_dir = tmp_path / "audit"
    logger = AuditLogger(audit_dir=audit_dir)
    assert logger._dir == audit_dir
    assert logger._path == audit_dir / "audit.jsonl"
    assert audit_dir.exists()

def test_log_tool_call_sanitization(tmp_path):
    audit_dir = tmp_path / "audit"
    logger = AuditLogger(audit_dir=audit_dir)

    logger.log_tool_call(
        tool_name="test_tool",
        arguments={"password": "123", "normal": "val"},
        success=True
    )

    entries = logger.recent_entries(count=1)
    assert len(entries) == 1
    assert entries[0]["type"] == "tool_call"
    assert entries[0]["args"]["password"] == "***REDACTED***"
    assert entries[0]["args"]["normal"] == "val"

def test_write_jsonl(tmp_path):
    audit_dir = tmp_path / "audit"
    logger = AuditLogger(audit_dir=audit_dir)

    entry = {"event": "test"}
    logger._write(entry)

    with open(audit_dir / "audit.jsonl", "r") as f:
        line = f.read()
        data = json.loads(line)
        assert data["event"] == "test"
        assert "ts" in data
        assert "pid" in data

def test_recent_entries(tmp_path):
    audit_dir = tmp_path / "audit"
    logger = AuditLogger(audit_dir=audit_dir)

    for i in range(5):
        logger._write({"index": i})

    entries = logger.recent_entries(count=2)
    assert len(entries) == 2
    assert entries[0]["index"] == 3
    assert entries[1]["index"] == 4
