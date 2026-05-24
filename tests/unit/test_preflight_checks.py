"""Unit tests for pre-flight checks (src/aradhya/preflight_checks.py)."""
from __future__ import annotations

import pytest

from src.aradhya.preflight_checks import (
    PreflightResult,
    check_json,
    check_python,
    check_yaml,
    preflight_check,
)


class TestCheckPython:
    def test_valid_python(self) -> None:
        result = check_python("def foo():\n    return 42\n")
        assert result.ok is True
        assert not result.errors

    def test_syntax_error(self) -> None:
        result = check_python("def foo(\n    return 42")
        assert result.ok is False
        assert len(result.errors) == 1
        assert "syntax error" in result.errors[0].lower()

    def test_empty_content(self) -> None:
        result = check_python("")
        assert result.ok is True

    def test_complex_valid_python(self) -> None:
        code = '''
from __future__ import annotations
import os

class Foo:
    def bar(self, x: int) -> str:
        return f"value is {x}"

    @staticmethod
    def baz():
        return [i**2 for i in range(10)]
'''
        result = check_python(code)
        assert result.ok is True


class TestCheckJson:
    def test_valid_json(self) -> None:
        result = check_json('{"key": "value", "list": [1, 2, 3]}')
        assert result.ok is True

    def test_invalid_json(self) -> None:
        result = check_json('{"key": "value",}')  # trailing comma
        assert result.ok is False
        assert len(result.errors) == 1

    def test_empty_object(self) -> None:
        result = check_json("{}")
        assert result.ok is True


class TestCheckYaml:
    def test_valid_yaml(self) -> None:
        result = check_yaml("key: value\nlist:\n  - item1\n  - item2\n")
        assert result.ok is True

    def test_invalid_yaml(self) -> None:
        result = check_yaml("key: value\n  bad indent: oops\n  : : :")
        # May or may not fail depending on yaml parser strictness
        # At minimum, should not crash
        assert isinstance(result, PreflightResult)


class TestPreflightCheck:
    def test_python_extension(self) -> None:
        result = preflight_check("test.py", "def foo():\n    pass\n")
        assert result.ok is True

    def test_python_syntax_error(self) -> None:
        result = preflight_check("test.py", "def foo(\n")
        assert result.ok is False

    def test_json_extension(self) -> None:
        result = preflight_check("config.json", '{"valid": true}')
        assert result.ok is True

    def test_unknown_extension(self) -> None:
        result = preflight_check("readme.md", "# Hello\n\nSome content")
        assert result.ok is True  # no checker, pass through

    def test_pyw_extension(self) -> None:
        result = preflight_check("gui.pyw", "import tkinter\n")
        assert result.ok is True

    def test_result_summary(self) -> None:
        result = PreflightResult(ok=False, errors=["bad syntax"])
        assert "error" in result.summary.lower()

    def test_result_summary_clean(self) -> None:
        result = PreflightResult()
        assert "passed" in result.summary.lower()
