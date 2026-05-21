"""Wildcard-based permission rules engine.

Replaces the boolean ``allow_live_execution`` flag with a pattern-based
permission system inspired by Claude Code:

- ``allow`` rules: permit matching tool calls without confirmation
- ``deny`` rules: block matching tool calls unconditionally
- **Deny always overrides allow** (security invariant)

Rule format examples::

    run_command(npm *)       — any npm command
    run_command(git *)       — any git command
    write_file(*.py)         — Python files only
    run_command(rm -rf *)    — dangerous rm (deny this!)
    read_file               — any read_file call (no arg filter)

Configuration lives in:
    ``~/.aradhya/permissions.json``
    ``<project>/.aradhya/permissions.json``
"""

from __future__ import annotations

import fnmatch
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class PermissionDecision:
    """The outcome of a permission check."""
    allowed: bool = True
    reason: str = ""
    matched_rule: str = ""
    requires_confirmation: bool = False


@dataclass
class PermissionRule:
    """A single permission rule."""
    tool_name: str          # e.g. "run_command"
    arg_pattern: str = ""   # e.g. "npm *", empty = match any args
    raw: str = ""           # original rule string for display

    def matches(self, tool_name: str, arguments: dict[str, Any]) -> bool:
        """Check if this rule matches a given tool call."""
        if self.tool_name != tool_name and self.tool_name != "*":
            return False

        if not self.arg_pattern:
            return True

        # Build a string representation of the arguments for matching
        arg_str = _arguments_to_match_string(tool_name, arguments)
        return fnmatch.fnmatch(arg_str, self.arg_pattern)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

_RULE_RE = re.compile(
    r"^(?P<tool>\w+)(?:\((?P<pattern>[^)]*)\))?$"
)


def parse_rule(raw: str) -> PermissionRule | None:
    """Parse a rule string like ``run_command(npm *)`` into a PermissionRule."""
    raw = raw.strip()
    if not raw:
        return None

    match = _RULE_RE.match(raw)
    if not match:
        logger.warning("Invalid permission rule: {}", raw)
        return None

    return PermissionRule(
        tool_name=match.group("tool"),
        arg_pattern=match.group("pattern") or "",
        raw=raw,
    )


def _arguments_to_match_string(tool_name: str, arguments: dict[str, Any]) -> str:
    """Convert tool arguments to a flat string for pattern matching.

    For ``run_command``, uses the 'command' arg.
    For ``write_file``, uses the 'path' arg.
    Otherwise, joins all string values with spaces.
    """
    if tool_name == "run_command":
        return str(arguments.get("command", ""))
    if tool_name in ("write_file", "read_file", "delete_file", "move_file"):
        return str(arguments.get("path", arguments.get("file_path", "")))
    if tool_name in ("open_url", "open_path"):
        return str(arguments.get("url", arguments.get("path", "")))
    # Fallback: join all string values
    parts = [str(v) for v in arguments.values() if isinstance(v, str)]
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Permission Engine
# ---------------------------------------------------------------------------

class PermissionEngine:
    """Checks tool calls against allow/deny rules.

    Rules are evaluated in order:
    1. Deny rules are checked first — if any match, the call is BLOCKED
    2. Allow rules are checked — if any match, the call is ALLOWED
    3. If no rule matches, falls through to the default policy
    """

    def __init__(
        self,
        allow_rules: list[PermissionRule] | None = None,
        deny_rules: list[PermissionRule] | None = None,
        default_requires_confirmation: bool = True,
    ) -> None:
        self.allow_rules = allow_rules or []
        self.deny_rules = deny_rules or []
        self.default_requires_confirmation = default_requires_confirmation

    def check(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> PermissionDecision:
        """Evaluate a tool call against rules.

        Returns a PermissionDecision indicating whether the call is
        allowed, denied, or needs confirmation.
        """
        # 1. Deny rules first (deny always wins)
        for rule in self.deny_rules:
            if rule.matches(tool_name, arguments):
                logger.debug(
                    "Permission DENIED: tool={} matched deny rule '{}'",
                    tool_name,
                    rule.raw,
                )
                return PermissionDecision(
                    allowed=False,
                    reason=f"Blocked by deny rule: {rule.raw}",
                    matched_rule=rule.raw,
                )

        # 2. Allow rules
        for rule in self.allow_rules:
            if rule.matches(tool_name, arguments):
                logger.debug(
                    "Permission ALLOWED: tool={} matched allow rule '{}'",
                    tool_name,
                    rule.raw,
                )
                return PermissionDecision(
                    allowed=True,
                    reason=f"Matched allow rule: {rule.raw}",
                    matched_rule=rule.raw,
                )

        # 3. Default: fall through to confirmation gate
        return PermissionDecision(
            allowed=True,
            requires_confirmation=self.default_requires_confirmation,
            reason="No rule matched — default policy",
        )


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def load_permissions(
    project_root: Path | None = None,
    *,
    user_config_dir: Path | None = None,
) -> PermissionEngine:
    """Load permission rules from user and project config.

    Config format (``permissions.json``)::

        {
          "allow": [
            "run_command(npm *)",
            "run_command(git *)",
            "read_file",
            "search_files"
          ],
          "deny": [
            "run_command(rm -rf *)",
            "delete_file"
          ]
        }
    """
    config_dir = user_config_dir or (Path.home() / ".aradhya")
    allow_rules: list[PermissionRule] = []
    deny_rules: list[PermissionRule] = []

    # Load from user-level
    _load_from_file(config_dir / "permissions.json", allow_rules, deny_rules)

    # Load from project-level (additive)
    if project_root is not None:
        _load_from_file(
            project_root / ".aradhya" / "permissions.json",
            allow_rules,
            deny_rules,
        )

    engine = PermissionEngine(
        allow_rules=allow_rules,
        deny_rules=deny_rules,
    )

    if allow_rules or deny_rules:
        logger.info(
            "Permission engine loaded: {} allow rules, {} deny rules",
            len(allow_rules),
            len(deny_rules),
        )

    return engine


def _load_from_file(
    filepath: Path,
    allow_rules: list[PermissionRule],
    deny_rules: list[PermissionRule],
) -> None:
    """Load rules from a single permissions.json file."""
    if not filepath.is_file():
        return

    try:
        data = json.loads(filepath.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load permissions from {}: {}", filepath, exc)
        return

    for raw in data.get("allow", []):
        rule = parse_rule(raw)
        if rule:
            allow_rules.append(rule)

    for raw in data.get("deny", []):
        rule = parse_rule(raw)
        if rule:
            deny_rules.append(rule)
