"""Unit tests for agent definitions (src/aradhya/agents/agent_defs.py)."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.aradhya.agents.agent_defs import (
    AgentDefinition,
    AgentRegistry,
    load_agent_from_file,
    load_agents,
    _parse_frontmatter,
)


class TestParseFrontmatter:
    def test_parses_simple_frontmatter(self) -> None:
        text = """---
name: test-agent
description: A test agent
model: qwen3:8b
color: green
---

You are a test agent.
"""
        meta, body = _parse_frontmatter(text)
        assert meta["name"] == "test-agent"
        assert meta["description"] == "A test agent"
        assert meta["model"] == "qwen3:8b"
        assert meta["color"] == "green"
        assert "You are a test agent." in body

    def test_no_frontmatter_returns_empty(self) -> None:
        text = "Just plain markdown without frontmatter."
        meta, body = _parse_frontmatter(text)
        assert meta == {}
        assert body == text

    def test_quoted_values_stripped(self) -> None:
        text = '---\nname: "my-agent"\ndescription: \'A desc\'\n---\nBody'
        meta, body = _parse_frontmatter(text)
        assert meta["name"] == "my-agent"
        assert meta["description"] == "A desc"

    def test_tools_with_commas(self) -> None:
        text = "---\ntools: Glob, Grep, Read, Bash\n---\nBody"
        meta, _ = _parse_frontmatter(text)
        assert meta["tools"] == "Glob, Grep, Read, Bash"


class TestLoadAgentFromFile:
    def test_load_valid_agent(self, tmp_path: Path) -> None:
        agent_file = tmp_path / "reviewer.md"
        agent_file.write_text(
            """---
name: code-reviewer
description: Reviews code for bugs
tools: read_file, search_files, run_command
model: qwen3:8b
color: red
maxTurns: 15
---

You are an expert code reviewer.

## Focus Areas
- Bug detection
- Code quality
""",
            encoding="utf-8",
        )

        agent = load_agent_from_file(agent_file)
        assert agent is not None
        assert agent.name == "code-reviewer"
        assert agent.description == "Reviews code for bugs"
        assert "read_file" in agent.tools
        assert "search_files" in agent.tools
        assert "run_command" in agent.tools
        assert agent.model == "qwen3:8b"
        assert agent.color == "red"
        assert agent.max_turns == 15
        assert "expert code reviewer" in agent.system_prompt
        assert agent.source_path == agent_file

    def test_name_defaults_to_filename(self, tmp_path: Path) -> None:
        agent_file = tmp_path / "architect.md"
        agent_file.write_text(
            "---\ndescription: Designs architecture\n---\nYou are an architect.",
            encoding="utf-8",
        )
        agent = load_agent_from_file(agent_file)
        assert agent is not None
        assert agent.name == "architect"

    def test_missing_file_returns_none(self, tmp_path: Path) -> None:
        agent = load_agent_from_file(tmp_path / "nonexistent.md")
        assert agent is None

    def test_isolation_worktree(self, tmp_path: Path) -> None:
        agent_file = tmp_path / "isolated.md"
        agent_file.write_text(
            "---\nname: isolated-agent\nisolation: worktree\nbackground: true\n---\nRun in isolation.",
            encoding="utf-8",
        )
        agent = load_agent_from_file(agent_file)
        assert agent is not None
        assert agent.isolation == "worktree"
        assert agent.background is True

    def test_tools_set_property(self, tmp_path: Path) -> None:
        agent_file = tmp_path / "tooled.md"
        agent_file.write_text(
            "---\nname: tooled\ntools: read_file, write_file\n---\nBody",
            encoding="utf-8",
        )
        agent = load_agent_from_file(agent_file)
        assert agent is not None
        assert agent.tools_set == frozenset({"read_file", "write_file"})


class TestAgentRegistry:
    def test_register_and_get(self) -> None:
        registry = AgentRegistry()
        agent = AgentDefinition(name="test", description="Test agent")
        registry.register(agent)
        assert registry.get("test") is agent
        assert registry.count == 1

    def test_get_missing_returns_none(self) -> None:
        registry = AgentRegistry()
        assert registry.get("nonexistent") is None

    def test_all_agents_sorted(self) -> None:
        registry = AgentRegistry()
        registry.register(AgentDefinition(name="zebra"))
        registry.register(AgentDefinition(name="alpha"))
        registry.register(AgentDefinition(name="middle"))
        agents = registry.all_agents()
        assert [a.name for a in agents] == ["alpha", "middle", "zebra"]


class TestLoadAgents:
    def test_load_from_user_dir(self, tmp_path: Path) -> None:
        user_dir = tmp_path / "agents"
        user_dir.mkdir()
        (user_dir / "helper.md").write_text(
            "---\nname: helper\ndescription: A helper\n---\nHelp!",
            encoding="utf-8",
        )
        registry = load_agents(user_agents_dir=user_dir)
        assert registry.count == 1
        assert registry.get("helper") is not None

    def test_project_overrides_user(self, tmp_path: Path) -> None:
        user_dir = tmp_path / "user_agents"
        user_dir.mkdir()
        (user_dir / "builder.md").write_text(
            "---\nname: builder\ndescription: User builder\nmodel: small\n---\nUser version.",
            encoding="utf-8",
        )

        project = tmp_path / "project"
        project_dir = project / ".aradhya" / "agents"
        project_dir.mkdir(parents=True)
        (project_dir / "builder.md").write_text(
            "---\nname: builder\ndescription: Project builder\nmodel: large\n---\nProject version.",
            encoding="utf-8",
        )

        registry = load_agents(
            project_root=project,
            user_agents_dir=user_dir,
        )
        agent = registry.get("builder")
        assert agent is not None
        assert agent.model == "large"
        assert agent.description == "Project builder"

    def test_empty_dirs_return_empty_registry(self, tmp_path: Path) -> None:
        registry = load_agents(user_agents_dir=tmp_path / "empty")
        assert registry.count == 0
