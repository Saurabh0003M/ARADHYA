from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from src.aradhya.learnings.learnings_engine import LearningsEngine, log_error, _ERRORS_HEADER

def test_learnings_engine_log_error_no_context(tmp_path):
    engine = LearningsEngine(tmp_path)

    with patch("src.aradhya.learnings.learnings_engine.datetime") as mock_datetime:
        mock_datetime.now.return_value.isoformat.return_value = "2023-01-01T12:00:00"
        mock_datetime.now.return_value.strftime.side_effect = ["20230101", "120000"]

        entry_id = engine.log_error(tool_name="test_tool", error_message="Something failed")

        assert entry_id == "ERR-20230101-120000"

        errors_file = tmp_path / "core" / "memory" / ".learnings" / "ERRORS.md"
        assert errors_file.exists()

        content = errors_file.read_text(encoding="utf-8")
        assert _ERRORS_HEADER in content
        assert "## [ERR-20230101-120000] test_tool" in content
        assert "**Logged**: 2023-01-01T12:00:00" in content
        assert "### Error\nSomething failed\n" in content
        assert "### Context" not in content

def test_learnings_engine_log_error_with_context(tmp_path):
    engine = LearningsEngine(tmp_path)

    with patch("src.aradhya.learnings.learnings_engine.datetime") as mock_datetime:
        mock_datetime.now.return_value.isoformat.return_value = "2023-01-01T12:00:00"
        mock_datetime.now.return_value.strftime.side_effect = ["20230101", "120000"]

        entry_id = engine.log_error(
            tool_name="test_tool",
            error_message="Something failed",
            context="Attempting to read non-existent file"
        )

        errors_file = tmp_path / "core" / "memory" / ".learnings" / "ERRORS.md"
        content = errors_file.read_text(encoding="utf-8")
        assert "### Error\nSomething failed\n" in content
        assert "### Context\nAttempting to read non-existent file\n" in content

def test_standalone_log_error_tool():
    with patch("src.aradhya.learnings.learnings_engine.LearningsEngine") as mock_engine_cls:
        mock_engine = mock_engine_cls.return_value
        mock_engine.log_error.return_value = "ERR-123"

        result = log_error("test_tool", "error details", "some context")

        mock_engine_cls.assert_called_once()
        mock_engine.log_error.assert_called_once_with("test_tool", "error details", "some context")
        assert result == "Error logged as ERR-123."
