"""Agent definitions loader.

Loads agent definitions from Markdown files with YAML frontmatter,
following the same convention as Claude Code:

.. code-block:: markdown

    ---
    name: code-reviewer
    description: Reviews code for bugs and style issues
    tools: read_file, search_files, run_command
    model: qwen3:8b
    color: red
    max_turns: 15
    ---

    You are a code reviewer specializing in Python...

Agents are loaded from:
    1. ``~/.aradhya/agents/*.md``
    2. ``<project>/.aradhya/agents/*.md``
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from src.aradhya.paths import agents_dir

from loguru import logger

# Match YAML frontmatter block: starts and ends with ---
_FRONTMATTER_RE = re.compile(
    r"\A---\s*\n(.*?)\n---\s*\n",
    re.DOTALL,
)

# Simple YAML-like key: value parser (avoids requiring pyyaml)
_KV_RE = re.compile(r"^(\w[\w-]*)\s*:\s*(.+)$", re.MULTILINE)


@dataclass
class AgentDefinition:
    """A parsed agent definition from a Markdown file."""

    name: str
    description: str = ""
    system_prompt: str = ""
    tools: list[str] = field(default_factory=list)
    disallowed_tools: list[str] = field(default_factory=list)
    model: str = ""
    color: str = ""
    max_turns: int = 10
    isolation: str = ""           # "worktree" for git worktree isolation
    background: bool = False      # always run as background task
    initial_prompt: str = ""      # auto-submit first turn
    source_path: Path | None = None

    @property
    def tools_set(self) -> frozenset[str]:
        return frozenset(self.tools)


class AgentRegistry:
    """Registry of available agent definitions."""

    def __init__(self) -> None:
        self._agents: dict[str, AgentDefinition] = {}

    def register(self, agent: AgentDefinition) -> None:
        """Register an agent definition."""
        self._agents[agent.name] = agent
        logger.debug("Registered agent: {}", agent.name)

    def get(self, name: str) -> AgentDefinition | None:
        """Retrieve an agent by name."""
        return self._agents.get(name)

    def all_agents(self) -> list[AgentDefinition]:
        """Return all registered agents sorted by name."""
        return sorted(self._agents.values(), key=lambda a: a.name)

    @property
    def count(self) -> int:
        return len(self._agents)


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Extract YAML frontmatter and body from a Markdown file.

    Returns a (metadata_dict, body) tuple.  Uses a simple key-value
    parser to avoid requiring PyYAML.
    """
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text

    frontmatter_block = match.group(1)
    body = text[match.end():]

    metadata: dict[str, str] = {}
    for kv_match in _KV_RE.finditer(frontmatter_block):
        key = kv_match.group(1).strip()
        value = kv_match.group(2).strip()
        # Strip surrounding quotes if present
        if len(value) >= 2 and value[0] in ('"', "'") and value[-1] == value[0]:
            value = value[1:-1]
        metadata[key] = value

    return metadata, body


def _parse_tools_list(raw: str) -> list[str]:
    """Parse a comma-separated or space-separated tools string."""
    # Handle both "Glob, Grep, Read" and "Glob Grep Read"
    return [t.strip() for t in re.split(r"[,\s]+", raw) if t.strip()]


def _parse_bool(raw: str) -> bool:
    """Parse a boolean value from YAML-like frontmatter."""
    return raw.lower() in ("true", "yes", "1", "on")


def load_agent_from_file(filepath: Path) -> AgentDefinition | None:
    """Load a single agent definition from a Markdown file."""
    try:
        text = filepath.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("Cannot read agent file {}: {}", filepath, exc)
        return None

    metadata, body = _parse_frontmatter(text)

    name = metadata.get("name", filepath.stem)
    if not name:
        return None

    return AgentDefinition(
        name=name,
        description=metadata.get("description", ""),
        system_prompt=body.strip(),
        tools=_parse_tools_list(metadata.get("tools", "")),
        disallowed_tools=_parse_tools_list(metadata.get("disallowedTools", "") or metadata.get("disallowed-tools", "")),
        model=metadata.get("model", ""),
        color=metadata.get("color", ""),
        max_turns=int(metadata.get("max_turns", metadata.get("maxTurns", "10"))),
        isolation=metadata.get("isolation", ""),
        background=_parse_bool(metadata.get("background", "false")),
        initial_prompt=metadata.get("initialPrompt", "") or metadata.get("initial-prompt", ""),
        source_path=filepath,
    )


def load_agents(
    project_root: Path | None = None,
    *,
    user_agents_dir: Path | None = None,
) -> AgentRegistry:
    """Load all agent definitions from user and project directories.

    Precedence: project-level agents override user-level agents with
    the same name.
    """
    registry = AgentRegistry()
    user_dir = user_agents_dir or agents_dir()

    # 1. User-level agents
    if user_dir.is_dir():
        for md_file in sorted(user_dir.glob("*.md")):
            agent = load_agent_from_file(md_file)
            if agent:
                registry.register(agent)

    # 2. Project-level agents (override user-level)
    if project_root is not None:
        project_dir = project_root / ".aradhya" / "agents"
        if project_dir.is_dir():
            for md_file in sorted(project_dir.glob("*.md")):
                agent = load_agent_from_file(md_file)
                if agent:
                    registry.register(agent)

    if registry.count > 0:
        logger.info("Loaded {} agent definition(s)", registry.count)

    return registry
