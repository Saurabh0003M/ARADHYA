"""Pre-flight checks for file writes and code modifications.

Inspired by gpt-engineer's lint-before-write pattern: before the
write_file tool commits content to disk, run quick syntax checks
that catch obvious errors the model introduced.  If a check fails,
the error is returned to the model so it can self-correct *before*
the broken file hits disk.

This module provides a registry of checkers keyed by file extension.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from dataclasses import dataclass, field

from loguru import logger


@dataclass
class PreflightResult:
    """Outcome of a pre-flight check."""
    ok: bool = True
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        parts = []
        if self.errors:
            parts.append(
                f"❌ {len(self.errors)} error(s):\n"
                + "\n".join(f"  • {e}" for e in self.errors)
            )
        if self.warnings:
            parts.append(
                f"⚠️  {len(self.warnings)} warning(s):\n"
                + "\n".join(f"  • {w}" for w in self.warnings)
            )
        return "\n".join(parts) if parts else "✅ All checks passed"


def check_python(content: str) -> PreflightResult:
    """Parse Python source with ast to catch syntax errors."""
    result = PreflightResult()
    try:
        ast.parse(content)
    except SyntaxError as exc:
        result.ok = False
        msg = f"Python syntax error at line {exc.lineno}: {exc.msg}"
        if exc.text:
            msg += f"\n    {exc.text.rstrip()}"
        result.errors.append(msg)
    return result


def check_json(content: str) -> PreflightResult:
    """Validate JSON syntax."""
    result = PreflightResult()
    try:
        json.loads(content)
    except json.JSONDecodeError as exc:
        result.ok = False
        result.errors.append(
            f"JSON syntax error at line {exc.lineno}, col {exc.colno}: {exc.msg}"
        )
    return result


def check_yaml(content: str) -> PreflightResult:
    """Validate YAML syntax (if PyYAML is available)."""
    result = PreflightResult()
    try:
        import yaml
        yaml.safe_load(content)
    except ImportError:
        # yaml not installed, skip silently
        pass
    except yaml.YAMLError as exc:
        result.ok = False
        result.errors.append(f"YAML syntax error: {exc}")
    return result


def check_toml(content: str) -> PreflightResult:
    """Validate TOML syntax (Python 3.11+ or tomli)."""
    result = PreflightResult()
    try:
        try:
            import tomllib  # Python 3.11+
        except ImportError:
            import tomli as tomllib  # type: ignore[no-redef]
        tomllib.loads(content)
    except ImportError:
        pass
    except Exception as exc:
        result.ok = False
        result.errors.append(f"TOML syntax error: {exc}")
    return result


# Extension -> checker mapping
_CHECKERS: dict[str, callable] = {
    ".py": check_python,
    ".pyw": check_python,
    ".json": check_json,
    ".jsonl": check_json,
    ".yaml": check_yaml,
    ".yml": check_yaml,
    ".toml": check_toml,
}


def preflight_check(filepath: str, content: str) -> PreflightResult:
    """Run pre-flight checks for the given file content.

    Selects the appropriate checker based on file extension.
    If no checker exists for the extension, returns OK.

    Args:
        filepath: Target file path (used for extension detection)
        content: Content that will be written

    Returns:
        PreflightResult with ok=True if no errors found
    """
    ext = Path(filepath).suffix.lower()
    checker = _CHECKERS.get(ext)

    if checker is None:
        return PreflightResult()  # no checker, pass

    try:
        result = checker(content)
        if not result.ok:
            logger.warning(
                "Pre-flight check failed for {}: {}",
                filepath,
                result.summary,
            )
        return result
    except Exception as exc:
        # Never let a checker crash block the write
        logger.warning("Pre-flight checker crashed for {}: {}", filepath, exc)
        return PreflightResult()
