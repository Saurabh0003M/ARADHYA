"""Hook configuration loader.

Loads hook definitions from:
1. ``~/.aradhya/hooks/hooks.json``  (user-level)
2. ``<project>/.aradhya/hooks/hooks.json``  (project-level)

The JSON format mirrors Claude Code's hooks.json:

.. code-block:: json

    {
      "hooks": {
        "PreToolUse": [
          {
            "hooks": [
              {
                "type": "command",
                "command": "python hooks/pretooluse.py",
                "timeout": 10,
                "once": false,
                "matcher": "run_command"
              }
            ]
          }
        ]
      }
    }
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loguru import logger

from src.aradhya.hooks.hook_engine import (
    HookDefinition,
    HookEngine,
    HookEvent,
    HookType,
)

# Default user hooks directory
_USER_HOOKS_DIR = Path.home() / ".aradhya" / "hooks"


def load_hooks_from_file(hooks_file: Path) -> list[HookDefinition]:
    """Parse a hooks.json file and return HookDefinition objects."""
    if not hooks_file.is_file():
        return []

    try:
        data = json.loads(hooks_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load hooks from {}: {}", hooks_file, exc)
        return []

    hooks_section = data.get("hooks", {})
    definitions: list[HookDefinition] = []

    for event_name, event_entries in hooks_section.items():
        # Validate event name
        try:
            event = HookEvent(event_name)
        except ValueError:
            logger.warning("Unknown hook event '{}' in {}", event_name, hooks_file)
            continue

        for entry in event_entries:
            for hook_spec in entry.get("hooks", []):
                hook_type_str = hook_spec.get("type", "command")

                if hook_type_str != "command":
                    logger.debug(
                        "Skipping non-command hook type '{}' in {}",
                        hook_type_str,
                        hooks_file,
                    )
                    continue

                command = hook_spec.get("command", "")
                if not command:
                    continue

                # Resolve ${ARADHYA_HOOKS_ROOT} placeholder
                command = command.replace(
                    "${ARADHYA_HOOKS_ROOT}",
                    str(hooks_file.parent),
                )

                definitions.append(
                    HookDefinition(
                        event=event,
                        hook_type=HookType.COMMAND,
                        command=command,
                        timeout_seconds=hook_spec.get("timeout", 10),
                        once=hook_spec.get("once", False),
                        matcher=hook_spec.get("matcher"),
                    )
                )

    logger.debug(
        "Loaded {} hook(s) from {}",
        len(definitions),
        hooks_file,
    )
    return definitions


def load_hooks(
    project_root: Path | None = None,
    *,
    user_hooks_dir: Path | None = None,
) -> HookEngine:
    """Build a HookEngine with hooks from user and project config.

    Loads in precedence order (later overrides earlier):
    1. User-level: ``~/.aradhya/hooks/hooks.json``
    2. Project-level: ``<project>/.aradhya/hooks/hooks.json``
    """
    engine = HookEngine()
    hooks_dir = user_hooks_dir or _USER_HOOKS_DIR

    # 1. User-level hooks
    user_file = hooks_dir / "hooks.json"
    engine.register_all(load_hooks_from_file(user_file))

    # 2. Project-level hooks
    if project_root is not None:
        project_file = project_root / ".aradhya" / "hooks" / "hooks.json"
        engine.register_all(load_hooks_from_file(project_file))

    if engine.total_hooks > 0:
        logger.info(
            "Hook engine loaded with {} hook(s) across {} event(s)",
            engine.total_hooks,
            sum(1 for e in HookEvent if engine.hooks_for(e)),
        )

    return engine


def create_default_hooks_config(target_dir: Path) -> Path:
    """Create a default hooks.json template in the given directory.

    Returns the path to the created file.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    hooks_file = target_dir / "hooks.json"

    if hooks_file.exists():
        return hooks_file

    default_config: dict[str, Any] = {
        "description": "ARADHYA hook configuration",
        "hooks": {
            "PreToolUse": [],
            "PostToolUse": [],
            "Stop": [],
            "SessionStart": [],
        },
    }

    hooks_file.write_text(
        json.dumps(default_config, indent=2),
        encoding="utf-8",
    )
    logger.info("Created default hooks config at {}", hooks_file)
    return hooks_file
