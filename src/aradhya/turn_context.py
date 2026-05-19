"""Per-turn context injection for the agent system prompt.

Inspired by Codex's ``turn_context`` protocol, this module builds a
structured context payload injected into the system prompt at every user
turn.  It gives the model reliable situational awareness of:

- Current working directory and timestamp
- The full read/write permission matrix (which paths it can touch)
- Execution policy (live execution status)
- Active session identifier

This replaces ad-hoc policy descriptions with a machine-parseable,
deterministic context block.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.aradhya.tools.runtime_policy import ToolRuntimePolicy


def _generate_turn_id() -> str:
    """Generate a compact, unique turn identifier."""
    return f"turn_{uuid.uuid4().hex[:12]}"


@dataclass(frozen=True)
class TurnContext:
    """Structured context injected at the start of each agent turn.

    Mirrors the ``turn_context`` event from Codex's session protocol.
    """

    turn_id: str
    session_id: str
    cwd: str
    timestamp: str
    timezone: str
    execution_policy: str  # "live" | "dry-run"
    permission_profile: dict[str, Any] = field(default_factory=dict)

    def to_prompt_block(self) -> str:
        """Format as a prompt injection block for the LLM system prompt."""
        lines = [
            "[Turn Context]",
            f"Turn: {self.turn_id}",
            f"Session: {self.session_id}",
            f"Time: {self.timestamp} ({self.timezone})",
            f"CWD: {self.cwd}",
            f"Execution policy: {self.execution_policy}",
        ]

        profile = self.permission_profile
        read_roots = profile.get("read_roots", [])
        write_roots = profile.get("write_roots", [])

        if read_roots:
            lines.append(f"Read access: {', '.join(str(r) for r in read_roots)}")
        if write_roots:
            lines.append(f"Write access: {', '.join(str(r) for r in write_roots)}")

        network = profile.get("network", "restricted")
        lines.append(f"Network: {network}")

        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for audit logging."""
        return {
            "turn_id": self.turn_id,
            "session_id": self.session_id,
            "cwd": self.cwd,
            "timestamp": self.timestamp,
            "timezone": self.timezone,
            "execution_policy": self.execution_policy,
            "permission_profile": self.permission_profile,
        }


def build_turn_context(
    policy: ToolRuntimePolicy,
    session_id: str = "",
    turn_id: str | None = None,
) -> TurnContext:
    """Build a fresh ``TurnContext`` from the current runtime state.

    Parameters
    ----------
    policy
        The active runtime policy governing tool execution.
    session_id
        The current session identifier.
    turn_id
        Optional explicit turn ID (generated if omitted).
    """
    now = datetime.now(timezone.utc)

    # Build permission profile from the policy
    permission_profile = policy.to_permission_profile()

    # Determine execution policy label
    if policy.live_execution_enabled and policy.mutation_granted:
        exec_policy = "live"
    elif policy.live_execution_enabled:
        exec_policy = "live (pending task confirmation)"
    else:
        exec_policy = "dry-run"

    # Detect timezone name
    try:
        import time as _time
        tz_name = _time.tzname[_time.daylight] if _time.daylight else _time.tzname[0]
    except Exception:
        tz_name = "UTC"

    return TurnContext(
        turn_id=turn_id or _generate_turn_id(),
        session_id=session_id,
        cwd=str(Path.cwd()),
        timestamp=now.isoformat(timespec="seconds"),
        timezone=tz_name,
        execution_policy=exec_policy,
        permission_profile=permission_profile,
    )
